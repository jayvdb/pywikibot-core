# -*- coding: utf-8  -*-
"""Installer script for Pywikibot 2.0 framework."""
#
# (C) Pywikibot team, 2009-2013
#
# Distributed under the terms of the MIT license.
#
__version__ = '$Id$'
#

import sys
import os
import itertools

test_deps = []

dependencies = ['httplib2>=0.9.0']

extra_deps = {
    # Core library dependencies
    'daemonize': ['daemonize'],
    'Graphviz':  ['pydot'],
    'MySQL': ['oursql'],
    'Yahoo': ['yahoo'],
    'Google': ['google'],
    'IRC': ['irc'],
    'mwparserfromhell': ['mwparserfromhell>=0.3.3']
}

if sys.version_info[0] == 2:
    extra_deps['wikistats-csv'] = ['unicodecsv']

script_deps = {
    'script_wui.py': ['irc', 'lunatic-python', 'crontab'],
    # Note: None of the 'lunatic-python' repos on github support MS Windows.
    'flickrripper.py': ['Pillow'],
    'states_redirect.py': ['pycountry']
}
# flickrapi 1.4.4 installs a root logger in verbose mode.
# The fix has been merged, but not released.  The problem doesnt exist
# in flickrapi 2.x.
# pywikibot uses flickrapi 1.4.x on Python 2, as it has been stable for a
# long time, and only depends on python-requests 1.x, whereas flickrapi 2.x
# depends on python-requests 2.x, which is first packaged in Ubuntu 14.04
# and will be first packaged for Fedora Core 21.
# flickrapi 1.4.x does not run on Python 3, and setuptools will
# automatically select flickrapi 2.x for Python 3 installs.
script_deps['flickrripper.py'].append('flickrapi>=1.4.5'
                                      if sys.version_info[0] == 2
                                      else 'flickrapi')

dependency_links = [
    'https://git.wikimedia.org/zip/?r=pywikibot/externals/httplib2.git&format=gz#egg=httplib2-0.8-pywikibot1',
    'git+https://github.com/AlereDevices/lunatic-python.git#egg=lunatic-python',
    'git+https://github.com/jayvdb/parse-crontab.git#egg=crontab',
]

if sys.version_info[0] == 2:
    if sys.version_info < (2, 6, 5):
        raise RuntimeError("ERROR: Pywikibot only runs under Python 2.6.5 or higher")
    elif sys.version_info[1] == 6:
        # work around distutils hardcoded unittest dependency
        import unittest  # noqa
        if 'test' in sys.argv and sys.version_info < (2, 7):
            import unittest2
            sys.modules['unittest'] = unittest2

        script_deps['replicate_wiki.py'] = ['argparse']
        dependencies.append('ordereddict')

if sys.version_info[0] == 3:
    if sys.version_info[1] < 3:
        print("ERROR: Python 3.3 or higher is required!")
        sys.exit(1)

if os.name != 'nt':
    # See bug 66010, Windows users will have issues
    # when trying to build the C modules.
    dependencies += extra_deps['mwparserfromhell']

if os.name == 'nt':
    # FIXME: tests/ui_tests.py suggests pywinauto 0.4.2
    # which isnt provided on pypi.
    test_deps += ['pywin32>=218', 'pywinauto>=0.4.0']

extra_deps.update(script_deps)
# Add script dependencies as test dependencies,
# so scripts can be compiled in test suite.
if 'PYSETUP_TEST_EXTRAS' in os.environ:
    test_deps += list(itertools.chain(*(script_deps.values())))

# late import of setuptools due to monkey-patching above
from ez_setup import use_setuptools
use_setuptools()

from setuptools import setup, find_packages

name = 'pywikibot'
version = '2.0b2'
github_url = 'https://github.com/wikimedia/pywikibot-core'
download_url = github_url + '/archive/master.zip#egg=' + name + '-' + version

setup(
    name=name,
    version=version,
    description='Python MediaWiki Bot Framework',
    long_description=open('README.rst').read(),
    maintainer='The pywikibot team',
    maintainer_email='pywikipedia-l@lists.wikimedia.org',
    license='MIT License',
    packages=['pywikibot'] + [package
                              for package in find_packages()
                              if package.startswith('pywikibot.')],
    install_requires=dependencies,
    dependency_links=dependency_links,
    extras_require=extra_deps,
    url='https://www.mediawiki.org/wiki/Pywikibot',
    download_url=download_url,
    test_suite="tests.collector",
    tests_require=test_deps,
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Development Status :: 4 - Beta',
        'Operating System :: OS Independent',
        'Intended Audience :: Developers',
        'Environment :: Console',
        'Programming Language :: Python :: 2.7'
    ],
    use_2to3=False
)
