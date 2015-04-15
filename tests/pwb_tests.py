# -*- coding: utf-8  -*-
"""
Test pwb.py.

If pwb.py does not load python files as expected, more tests from coverage
should be added locally.
https://bitbucket.org/ned/coveragepy/src/default/tests/test_execfile.py
"""
#
# (C) Pywikibot team, 2007-2014
#
# Distributed under the terms of the MIT license.
#
from __future__ import unicode_literals

__version__ = '$Id$'

import os
import sys

from tests import _tests_dir
from tests.utils import execute, execute_pwb
from tests.aspects import unittest, PwbTestCase

testbasepath = os.path.join(_tests_dir, 'pwb')

print_unicode_test_package = 'tests.pwb.print_unicode'
print_unicode_test_script = os.path.join(testbasepath, 'print_unicode.py')

print_locals_test_package = 'tests.pwb.print_locals'
print_locals_test_script = os.path.join(testbasepath, 'print_locals.py')

print_env_test_package = 'tests.pwb.print_env'
print_env_test_script = os.path.join(testbasepath, 'print_env.py')


class TestPwb(PwbTestCase):

    """
    Test pwb.py functionality.

    This is registered as a Site test because it will not run
    without a user-config.py
    """

    # site must be explicitly set for pwb tests. This test does not require
    # network access, because tests/pwb/print_locals.py does not use
    # handle_args, etc. so version.py doesnt talk on the network.
    site = False
    net = False

    def test_unicode(self):
        """
        Test internal environment of pywikibot.

        Make sure the environment is not contaminated, and is the same as
        the environment we get when directly running a script.
        """
        direct = execute([sys.executable, '-m', print_unicode_test_package])
        vpwb = execute_pwb([print_unicode_test_script])
        self.maxDiff = None
        self.assertEqual(direct['stdout'], vpwb['stdout'])

        self.assertEqual('Häuser', direct['stdout'].strip())
        self.assertEqual('Häuser', direct['stderr'].strip())
        self.assertEqual('Häuser', vpwb['stdout'].strip())
        self.assertEqual('Häuser', vpwb['stderr'].strip())

    def test_locals(self):
        """
        Test internal environment of pywikibot.

        Make sure the environment is not contaminated, and is the same as
        the environment we get when directly running a script.
        """
        direct = execute([sys.executable, '-m', print_locals_test_package])
        vpwb = execute_pwb([print_locals_test_script])
        self.maxDiff = None
        self.assertEqual(direct['stdout'], vpwb['stdout'])

    def test_env(self):
        """
        Test external environment of pywikibot.

        Make sure the environment is not contaminated, and is the same as
        the environment we get when directly running a script.
        """
        direct = execute([sys.executable, '-m', print_env_test_package])
        vpwb = execute_pwb([print_env_test_script])
        self.maxDiff = None
        self.assertEqual(direct['stdout'], vpwb['stdout'])


if __name__ == "__main__":
    unittest.main(verbosity=10)
