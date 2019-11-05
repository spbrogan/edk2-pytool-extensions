## @file test_edk2_pr_eval.py
# This contains unit tests for classes used in edk2_pr_eval
##
# Copyright (c) Microsoft Corporation
#
# SPDX-License-Identifier: BSD-2-Clause-Patent
##
import os
import tempfile
import unittest
import logging
from edk2toolext.invocables.edk2_pr_eval import DiffToPackageResolver


class Test_DiffToPackageResolver(unittest.TestCase):

    def test_is_public_file(self):
        pass


if __name__ == '__main__':
    unittest.main()
