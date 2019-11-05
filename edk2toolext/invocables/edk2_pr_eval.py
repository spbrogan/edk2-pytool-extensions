# @file edk2_pr_eval
# Checks the diff between a branch and head and then identifies
# if the requested packages need to be built.
##
# Copyright (c) Microsoft Corporation
#
# SPDX-License-Identifier: BSD-2-Clause-Patent
##

import os
import logging
from io import StringIO
from edk2toolext import edk2_logging
from edk2toolext.invocables.edk2_multipkg_aware_invocable import Edk2MultiPkgAwareInvocable
from edk2toolext.invocables.edk2_multipkg_aware_invocable import MultiPkgAwareSettingsInterface
from edk2toollib.uefi.edk2 import path_utilities
from edk2toollib.uefi.edk2.parsers.dec_parser import DecParser
from edk2toollib.uefi.edk2.parsers.inf_parser import InfParser
from edk2toollib.utility_functions import RunCmd


class PrEvalSettingsManager(MultiPkgAwareSettingsInterface):
    ''' Platform settings will be accessed through this implementation. '''

    def FilterPackagesToTest(self, changedFilesList: list, potentialPackagesList: list) -> list:
        ''' Filter potential packages to test based on changed files.
            Param:
              ChangedFilesList: list of edk2 relative paths to files that changed
              potentialPackagesList: list of edk2 packages to determine if should build
            return:
              list of edk2 packages that should be built from the potential list
        '''

        # default implementation does zero filtering.  Build them all.
        return potentialPackagesList
    
    def GetPackagesPath(self):
        ''' Return a list of workspace relative paths that should be mapped as edk2 PackagesPath '''

        # default implementation returns none
        return []


class Edk2PrEval(Edk2MultiPkgAwareInvocable):
    ''' Evaluate the changes and determine what packages of the supplied packages should
        be tested based on impact from the changes '''

    def AddCommandLineOptions(self, parserObj):
        ''' adds command line options to the argparser '''
        parserObj.add_argument("--pr-target", dest='pr_target', type=str, default=None,
                               help="PR Branch Target.  Allows build optimizations for pull request"
                               " validation based on files changed. If a package doesn't need testing then it will"
                               " be skipped. Example --pr-target origin/master", required=True)
        parserObj.add_argument("--output-csv-format-string", dest='output_csv_format_string', type=str, default=None,
                               help="Provide format string that will be output to stdout a full csv of packages"
                               " to be tested.  Valid Tokens: {pkgcsv}"
                               " Example --output-csv-format-string test={pkgcsv}")
        parserObj.add_argument("--output-count-format-string", dest='output_count_format_string', type=str,
                               default=None, help="Provide format string that will be output to stdout the count of"
                               " packages to be tested.  Valid Tokens: {pkgcount}"
                               " Example --output-count-format-string PackageCount={pkgcount}")

        super().AddCommandLineOptions(parserObj)

    def RetrieveCommandLineOptions(self, args):
        '''  Retrieve command line options from the argparser '''
        self.pr_target = args.pr_target
        self.output_csv_format_string = args.output_csv_format_string
        self.output_count_format_string = args.output_count_format_string
        super().RetrieveCommandLineOptions(args)

    def GetVerifyCheckRequired(self):
        ''' Will not call self_describing_environment.VerifyEnvironment because it might not be set up yet '''
        return False

    def GetSettingsClass(self):
        '''  Providing PrEvalSettingsManager  '''
        return PrEvalSettingsManager

    def GetLoggingFileName(self, loggerType):
        return "PREVALLOG"

    def Go(self):
        workspace_path = self.GetWorkspaceRoot()
        self.edk2_path_obj = path_utilities.Edk2Path(workspace_path, self.PlatformSettings.GetPackagesPath())
        self.logger = logging.getLogger("edk2_pr_eval")

        actualPackagesDict = {}
        package_resolver = DiffToPackageResolver(self.edk2_path_obj)
        (rc, files) = package_resolver.get_files_that_changed_in_this_pr(self.pr_target, os.path.abspath(os.getcwd()))
        if(rc == 0):
            actualPackagesDict = package_resolver.get_packages_to_build(
                files, self.requested_package_list, self.PlatformSettings.FilterPackagesToTest)
        else:
            self.logger.error("Failed to get changed files.  Build all packages.  RC = %d", rc)
            for a in self.requested_package_list:
                actualPackagesDict[a] = f"Policy 0 - Failed to diff ({rc})"

        #
        # Report the packages that need to be built
        #
        self.logger.log(edk2_logging.SECTION, "Output Results")
        self.logger.critical("Need to Build:")
        if len(actualPackagesDict.keys()) > 0:
            max_pkg_width = max(len(t) for t in actualPackagesDict.keys())
            for key, value in actualPackagesDict.items():
                self.logger.critical(f"{key:{max_pkg_width}}  Reason: {value}")
        else:
            self.logger.critical("None")

        #
        # If requested thru cmd line write to std out in defined format
        # This enabled CI pipelines
        #
        if self.output_csv_format_string is not None:
            pkgcsv = ",".join([x for x in actualPackagesDict.keys()])
            print(self.output_csv_format_string.format(pkgcsv=pkgcsv))

        if self.output_count_format_string is not None:
            pkgcount = len(actualPackagesDict.keys())
            print(self.output_count_format_string.format(pkgcount=pkgcount))

        return 0


class DiffToPackageResolver():
    ''' Evaluate a diff to resolve which packages need to be tested because they are impacted by the chaange'''

    def __init__(self, PathObj: path_utilities.Edk2Path):
        self.logger = logging.getLogger("DiffToPackageResolver")
        self.parsed_dec_cache = {}
        self.edk2_path_obj = PathObj

    def get_files_that_changed_in_this_pr(self, base_branch, working_dir) -> tuple:
        ''' Get all the files that changed in this pr.
            working_dir should be absolute path to git repo that is checked out
            with PR changes.

            Return the error code and list of files. 
            files are absolute path
        '''

        # get file differences between pr and base
        output = StringIO()
        cmd_params = f"diff --name-only HEAD..{base_branch}"
        rc = RunCmd("git", cmd_params, workingdir=working_dir, outstream=output)

        if(rc == 0):
            self.logger.debug("git diff command returned successfully!")
        else:
            self.logger.critical("git diff returned error return value: %s" % str(rc))
            return(rc, [])

        if(output.getvalue() is None):
            self.logger.info("No files listed in diff")
            return(0, [])

        files = output.getvalue().split()

        # convert to abs path because git repo root is not relevant in 
        # edk2 environment.  This should allow submodule
        files = [os.path.join(working_dir, f) for f in files]
        for f in files:
            self.logger.debug(f"File Changed: {f}")
        return(0, files)

    def get_packages_to_build(self, files: list, possible_packages: list, plat_func) -> dict:
        '''

        param:
          files: list of absolute file paths of files that changed
        '''

        remaining_packages = possible_packages.copy()  # start with all possible packages and remove each
        # package once it is determined to be build.  This optimization
        # avoids checking packages that already will be built.

        packages_to_build = {}  # packages to build.  Key = pkg name, Value = 1st reason for build
        edk2_relative_files = [self.edk2_path_obj.GetEdk2RelativePathFromAbsolutePath(f) for f in files]

        #
        # Policy 1 - platform function
        #
        after = plat_func(edk2_relative_files, remaining_packages.copy())
        for a in after:
            if a not in remaining_packages:
                raise ValueError(f"Platform Function FilterPackagesToTest returned package not allowed {a}")
            packages_to_build[a] = "Policy 1 - Platform Function - Filter Packages"
            remaining_packages.remove(a)

        #
        # Policy 2: Build any package that has changed
        #
        for f in files:
            try:
                pkg = self.edk2_path_obj.GetContainingPackage(os.path.abspath(f))

            except Exception as e:
                self.logger.error(f"Failed to get package for file {f}.  Exception {e}")
                # Ignore a file in which we fail to get the package
                continue

            if(pkg not in packages_to_build.keys() and pkg in remaining_packages):
                packages_to_build[pkg] = "Policy 2 - Build any package that has changed"
                remaining_packages.remove(pkg)

        #
        # Policy 3: If a file change is a public file then build all packages that
        #           are dependent on that package.
        #

        # list of packages with public files that have changed
        public_package_changes = []

        # Get all public files in packages
        for f in files:
            try:
                pkg = self.edk2_path_obj.GetContainingPackage(f)

            except Exception as e:
                self.logger.error(f"Failed to get package for file {f}.  Exception {e}")
                # Ignore a file in which we fail to get the package
                continue

            if self._is_public_file(f):
                public_package_changes.append(pkg)
        # de-duplicate list
        public_package_changes = list(set(public_package_changes))

        # Now check all remaining packages to see if they depend on the set of packages
        # with public file changes.
        # NOTE: future enhancement could be to check actual file dependencies
        for a in public_package_changes:
            for p in remaining_packages[:]:  # slice so we can delete as we go
                if(self._does_pkg_depend_on_package(p, a)):
                    packages_to_build[p] = f"Policy 3 - Package depends on {a}"
                    remaining_packages.remove(p)  # remove from remaining packages

        return packages_to_build

    def _does_pkg_depend_on_package(self, package_to_eval: str, support_package: str) -> bool:
        ''' return if any module in package_to_eval depends on public files defined in support_package'''
        # get filesystem path of package_to_eval
        abs_pkg_path = self.edk2_path_obj.GetAbsolutePathOnThisSytemFromEdk2RelativePath(package_to_eval)

        # loop thru all inf files in the package
        inf_files = self._walk_dir_for_filetypes([".inf"], abs_pkg_path)

        # compare if support_pkg in packages section
        # For each INF file
        for f in inf_files:
            ip = InfParser()
            ip.SetBaseAbsPath(self.edk2_path_obj.WorkspacePath).SetPackagePaths(
                self.edk2_path_obj.PackagePathList).ParseFile(f)

            for p in ip.PackagesUsed:
                if p.startswith(support_package):
                    self.logger.info(f"Module: {f} depends on package {support_package}")
                    return True
        # if never found return False
        return False

    def _parse_dec_for_package(self, path_to_package):
        ''' find DEC for package and parse it'''
        # find DEC file
        path = None
        try:
            allEntries = os.listdir(path_to_package)
            for entry in allEntries:
                if entry.lower().endswith(".dec"):
                    path = os.path.join(path_to_package, entry)
        except Exception:
            self.logger.error("Exception: Unable to find DEC for package:{0}".format(path_to_package))
            return None

        if path is None:
            self.logger.error("Unable to find DEC for package:{0}".format(path_to_package))
            return None

        wsr_dec_path = self.edk2_path_obj.GetEdk2RelativePathFromAbsolutePath(path)

        if path is None or wsr_dec_path == "" or not os.path.isfile(path):
            self.logger.error("Unable to convert path for DEC for package: {0}".format(path_to_package))
            return None

        # parse it
        dec = DecParser()
        dec.SetBaseAbsPath(self.edk2_path_obj.WorkspacePath).SetPackagePaths(self.edk2_path_obj.PackagePathList)
        dec.ParseFile(wsr_dec_path)
        return dec

    def _is_public_file(self, filepath):
        ''' return if file is a public files.
            filepath is absolute path
        '''
        self.logger.critical("Is public: " + filepath)
        try:
            pkg = self.edk2_path_obj.GetContainingPackage(filepath)
        except Exception as e:
            self.logger.error(f"Failed to GetContainingPackage({filepath}).  Exception: {str(e)}")
            return False

        dec = None
        if (pkg in self.parsed_dec_cache):
            dec = self.parsed_dec_cache[pkg]
        else:
            abs_pkg_path = self.edk2_path_obj.GetAbsolutePathOnThisSytemFromEdk2RelativePath(pkg)
            dec = self._parse_dec_for_package(abs_pkg_path)
            self.parsed_dec_cache[pkg] = dec

        if dec is None:
            self.logger.info(f"No package DEC file for {filepath}.")
            return False

        fp = filepath.replace("\\", "/")  # convert to edk2 sep
        #
        # Check to see if filepath has the include path as part of itself
        #
        for includepath in dec.IncludePaths:
            if (pkg + "/" + includepath + "/") in fp:
                return True

        #
        # Check to see if filepath is the DEC file.
        #
        if filepath.lower().endswith(".dec"):
            return True

        return False

    def _walk_dir_for_filetypes(self, extensionlist, directory, ignorelist=None):
        ''' Walks a directory for all items ending in certain extension '''

        if not isinstance(extensionlist, list):
            raise ValueError("Expected list but got " + str(type(extensionlist)))

        if directory is None:
            raise ValueError("No directory given")

        if not os.path.isabs(directory):
            raise ValueError("Directory not abs path")

        if not os.path.isdir(directory):
            raise ValueError("Invalid find directory to walk")

        if ignorelist is not None:
            ignorelist_lower = list()
            for item in ignorelist:
                ignorelist_lower.append(item.lower())

        extensionlist_lower = list()
        for item in extensionlist:
            extensionlist_lower.append(item.lower())

        returnlist = list()
        for Root, Dirs, Files in os.walk(directory):
            for File in Files:
                for Extension in extensionlist_lower:
                    if File.lower().endswith(Extension):
                        ignoreIt = False
                        if(ignorelist is not None):
                            for c in ignorelist_lower:
                                if(File.lower().startswith(c)):
                                    ignoreIt = True
                                    break
                        if not ignoreIt:
                            logging.debug(os.path.join(Root, File))
                            returnlist.append(os.path.join(Root, File))

        return returnlist


def main():
    Edk2PrEval().Invoke()
