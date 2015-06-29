"""Python 2 namespace package support."""
from __future__ import unicode_literals, absolute_import

import imp
import os
import sys

# A filename that exists in the real package directory
real_package_dir_contains = 'backports.py'


def get_real_package_dir(paths):
    """Get the real path for pywikibot."""
    for path in paths:
        if os.path.exists(os.path.join(path, real_package_dir_contains)):
            return path


def fix_package_import(paths, module_name):
    """Update pywikibot module with real pywikibot module."""
    if sys.version_info[0] > 2:
        return

    real_package_dir = get_real_package_dir(paths)
    assert real_package_dir

    real_init = os.path.join(real_package_dir, '__init__.py')
    module = imp.load_source(module_name, real_init)
    sys.modules[module_name] = module
