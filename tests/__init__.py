# -*- coding: utf-8  -*-
"""Package tests."""
#
# (C) Pywikibot team, 2007-2014
#
# Distributed under the terms of the MIT license.
#
from __future__ import unicode_literals

__version__ = '$Id$'

import os
import sys
import warnings

# Verify that the unit tests have a base working environment:
# - requests is mandatory
# - future is needed as a fallback for python 2.6,
#   however if unavailable this will fail on use; see pywikibot/tools.py
# - mwparserfromhell is optional, so is only imported in textlib_tests
try:
    import requests  # noqa
except ImportError as e:
    print("ImportError: %s" % e)
    sys.exit(1)

if sys.version_info < (2, 7, 3):
    # Unittest2 is a backport of python 2.7s unittest module to python 2.6
    # Also use unittest2 for python 2.7.2 (T106512)
    import unittest2 as unittest
else:
    import unittest

from pywikibot import config
from pywikibot import i18n

_tests_dir = os.path.split(__file__)[0]
_cache_dir = os.path.join(_tests_dir, '.webcache')
_data_dir = os.path.join(_tests_dir, 'data')
_images_dir = os.path.join(_data_dir, 'images')

# Find the root directory of the checkout
_root_dir = os.path.split(_tests_dir)[0]
_pwb_py = os.path.join(_root_dir, 'pwb.py')

library_test_modules = [
    'deprecation',
    'ui',
    'tests',
    'date',
    'mediawikiversion',
    'tools_chars',
    'tools_ip',
    'xmlreader',
    'textlib',
    'http',
    'namespace',
    'dry_api',
    'dry_site',
    'api',
    'family',
    'site',
    'link',
    'interwiki_link',
    'page',
    'category',
    'file',
    'edit_failure',
    'timestripper',
    'pagegenerators',
    'wikidataquery',
    'weblib',
    'i18n',
    'ui',
    'wikibase',
    'wikibase_edit',
    'upload',
]

script_test_modules = [
    'pwb',
    'script',
    'archivebot',
    'data_ingestion',
    'deletionbot',
    'cache',
]

disabled_test_modules = [
    'tests',  # tests of the tests package
    # weblib is deprecated, the tests fail for weblib,
    # but the tests are run in weblinkchecker_tests.
    'weblib',
]
if not i18n.messages_available():
    disabled_test_modules.append('l10n')

disabled_tests = {
    'textlib': [
        'test_interwiki_format',  # example; very slow test
    ],
    'site_detect': [
        'test_IWM',  # very slow and tests include unnecessary sites
    ],
}


def _unknown_test_modules():
    """List tests which are to be executed."""
    dir_list = os.listdir(_tests_dir)
    all_test_list = [name[0:-9] for name in dir_list  # strip '_tests.py'
                     if name.endswith('_tests.py') and
                     not name.startswith('_')]   # skip __init__.py and _*

    unknown_test_modules = [name
                            for name in all_test_list
                            if name not in library_test_modules and
                            name not in script_test_modules]

    return unknown_test_modules


extra_test_modules = sorted(_unknown_test_modules())

test_modules = library_test_modules + extra_test_modules + script_test_modules


def collector(loader=unittest.loader.defaultTestLoader):
    """Load the default modules.

    This is the entry point is specified in setup.py
    """
    # Note: Raising SkipTest during load_tests will
    # cause the loader to fallback to its own
    # discover() ordering of unit tests.
    if disabled_test_modules:
        print('Disabled test modules (to run: python -m unittest ...):\n  %s'
              % ', '.join(disabled_test_modules))

    if extra_test_modules:
        print('Extra test modules (run after library, before scripts):\n  %s'
              % ', '.join(extra_test_modules))

    if disabled_tests:
        print('Skipping tests (to run: python -m unittest ...):\n  %r'
              % disabled_tests)

    modules = [module
               for module in (library_test_modules +
                              extra_test_modules +
                              script_test_modules)
               if module not in disabled_test_modules]

    test_list = []

    for module in modules:
        module_class_name = 'tests.' + module + '_tests'
        if module in disabled_tests:
            discovered = loader.loadTestsFromName(module_class_name)
            enabled_tests = []
            for cls in discovered:
                for test_func in cls:
                    if test_func._testMethodName not in disabled_tests[module]:
                        enabled_tests.append(
                            module_class_name + '.' +
                            test_func.__class__.__name__ + '.' +
                            test_func._testMethodName)

            test_list.extend(enabled_tests)
        else:
            test_list.append(module_class_name)

    tests = loader.loadTestsFromNames(test_list)
    suite = unittest.TestSuite()
    suite.addTests(tests)
    return suite


def load_tests(loader=unittest.loader.defaultTestLoader,
               tests=None, pattern=None):
    """Load the default modules."""
    return collector(loader)


# Travis-CI builds are set to retry twice, which aims to reduce the number
# of 'red' builds caused by intermittant server problems, while also avoiding
# the builds taking a long time due to retries.
# The following allows builds to retry twice, but higher default values are
# overridden here to restrict retries to only 1, so developer builds fail more
# frequently in code paths resulting from mishandled server problems.
if config.max_retries > 2:
    if 'PYWIKIBOT_TEST_QUIET' not in os.environ:
        print('tests: max_retries reduced from %d to 1' % config.max_retries)
    config.max_retries = 1

cache_misses = 0
cache_hits = 0

warnings.filterwarnings("always")
