*** Settings ***
Documentation     A test suite to test Stuart Pr Eval
#
# Copyright (c), Microsoft Corporation
# SPDX-License-Identifier: BSD-2-Clause-Patent

Library  Process
Library  OperatingSystem
Library  String

Resource  Shared_Keywords.robot

Suite Setup  One time setup  ${repo_url}  ${ws_dir}

# --NOTE--
# Due to bug in pytool library the cwd of stuart_pr_eval needs to be in the Platforms directory
# https://github.com/tianocore/edk2-pytool-library/issues/105
#

*** Variables ***
${repo_url}           https://windowspartners@dev.azure.com/windowspartners/MSCoreUEFI/_git/mu_tiano_platforms
${master_branch}      CoreCiEnabled
# create a new repo so that we can be confident suart_setup/update/ci_setup has not been run since that
# is the critical test environment for the Pr_Eval step.
${ws_dir}             muplatabc
# changed due to bug 105
${platform_ci_file}   OvmfPkg${/}PlatformCI${/}PlatformBuild.py

${ws_root}            ${TEST_OUTPUT}${/}${ws_dir}





*** Keywords ***
One time setup
    [Arguments]  ${url}  ${folder}
    ## Dump pip versions
    ${result}=   Run Process    python  -m  pip   list  shell=True
    Log  ${result.stdout}

    ## Make output directory if doesn't already exist
    Create Directory  ${TEST_OUTPUT}

    ## Clone repo
    Run Keyword  Clone the git repo  ${url}  ${folder}

*** Test Cases ***


Test Stuart PR for all policies when a PR contains a deleted file
    [Tags]           PrEval  Delete  Edk2

    ${branch_name}=      Set Variable    PR_Rand_${{random.randint(0, 10000)}}
    ${file_to_modify}=   Set Variable    ReadMe.md

    Reset git repo to main branch  ${ws_root}  ${master_branch}
    Make new branch  ${branch_name}  ${ws_root}

    Remove File  ${ws_root}${/}${file_to_modify}

    Stage changed file  ${file_to_modify}  ${ws_root}
    Commit changes  "Changes"  ${ws_root}

    # changed due to bug 105
    ${pkgs}=  Stuart pr evaluation  ${platform_ci_file}  OvmfPkg  ${master_branch}  ${EMPTY}  ${ws_root}${/}Platforms
    Should Be Empty    ${pkgs}

    [Teardown]  Delete branch  ${branch_name}  ${master_branch}  ${ws_root}

Test Stuart PR for all policies when a PR contains file added
    [Tags]           PrEval  Add  Edk2

    ${branch_name}=       Set Variable    PR_Rand_${{random.randint(0, 10000)}}
    ${file_to_move}=      Set Variable    ReadMe.md
    # changed due to bug 105
    ${location_to_move}=  Set Variable    OvmfPkg${/}Library${/}LockBoxLib

    Reset git repo to main branch  ${ws_root}  ${master_branch}
    Make new branch  ${branch_name}  ${ws_root}

    Move File  ${ws_root}${/}${file_to_move}  ${ws_root}${/}${location_to_move}

    Stage changed file  ${location_to_move}  ${ws_root}
    Commit changes  "Changes"  ${ws_root}

    # changed due to bug 105
    ${pkgs}=  Stuart pr evaluation  ${platform_ci_file}  OvmfPkg  ${master_branch}  ${EMPTY}  ${ws_root}${/}Platforms
    Confirm same contents  ${pkgs}  OvmfPkg

    [Teardown]  Delete branch  ${branch_name}  ${master_branch}  ${ws_root}

Test Stuart PR for changing a file at the root of repo
    [Tags]           PrEval  Edk2

    ${branch_name}=      Set Variable    PR_Rand_${{random.randint(0, 10000)}}
    ${file_to_modify}=   Set Variable    pip-requirements.txt

    Reset git repo to main branch  ${ws_root}  ${master_branch}
    Make new branch  ${branch_name}  ${ws_root}

    Append To File  ${ws_root}${/}${file_to_modify}
    ...  Hello World!! Making a change for fun.

    Stage changed file  ${file_to_modify}  ${ws_root}
    Commit changes  "Changes"  ${ws_root}

    # changed due to bug 105
    ${pkgs}=  Stuart pr evaluation  ${platform_ci_file}  OvmfPkg  ${master_branch}  ${EMPTY}  ${ws_root}${/}Platforms
    Should Be Empty    ${pkgs}

    [Teardown]  Delete branch  ${branch_name}  ${master_branch}  ${ws_root}
