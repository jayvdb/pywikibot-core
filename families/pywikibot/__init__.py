"""Pywikibot extension package namespace init."""
from pkgutil import extend_path
__path__ = extend_path(__path__, __name__)
from pywikibot.tools.package_init import fix_package_import
fix_package_import(__path__, __name__)
