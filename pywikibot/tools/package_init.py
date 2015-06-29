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


class PEP420Loader(object):

    """Load a PEP420 namespace package in Python 2."""

    def __init__(self, fullname, path):
        """Constructor."""
        self.fullname = fullname
        self.path = path

    def load_module(self, fullname):
        """PEP 302 Loader."""
        mod = sys.modules.setdefault(fullname, imp.new_module(fullname))
        mod.__file__ = '<%s>' % self.__class__.__name__
        mod.__path__ = self.path
        mod.__package__ = fullname
        return mod


class PEP420Finder(object):

    """Treat identified packages as PEP420 namespace packages in Python 2."""

    def __init__(self, package_names):
        """Constructor."""
        self.package_names = package_names

    def find_module(self, fullname, path=None):
        """PEP 302 Finder."""
        if fullname not in self.package_names:
            return None
        assert path
        # The path is the parents path.
        # Append the subpackage directory to each item in the path.
        subpackage_name = fullname.rsplit('.')[1]
        path = [os.path.join(p, subpackage_name) for p in path]
        # instantiate a PEP420Loader with the revised path
        return PEP420Loader(fullname, path)


class PEP420Hook(object):

    """Hook in sys.meta_path to load PEP420 namespace packages in Python 2."""

    def __init__(self, package_names):
        """Constructor."""
        self.package_names = package_names

    def __call__(self, fullname):
        """Hook for sys.meta_path."""
        if fullname in self.package_names:
            return PEP420Finder


def install_package_namespace_loader(package_names):
    """Install a finder for namespace package support on Python 2."""
    sys.meta_path.append(PEP420Finder(package_names))
