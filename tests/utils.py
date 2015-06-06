# -*- coding: utf-8  -*-
"""Test utilities."""
#
# (C) Pywikibot team, 2013-2014
#
# Distributed under the terms of the MIT license.
#
from __future__ import print_function, unicode_literals
__version__ = '$Id$'
#
import json
import os
import re
import subprocess
import sys
import time
import traceback

from collections import Mapping
from warnings import warn

if sys.version_info[0] > 2:
    import six

    unicode = str

import pywikibot

from pywikibot import config
from pywikibot.comms import threadedhttp
from pywikibot.site import Namespace
from pywikibot.data.api import CachedRequest
from pywikibot.data.api import Request as _original_Request

from tests import _pwb_py
from tests import unittest  # noqa


class DrySiteNote(RuntimeWarning):

    """Information regarding dry site."""

    pass


def expected_failure_if(expect):
    """
    Unit test decorator to expect failure under conditions.

    @param expect: Flag to check if failure is expected
    @type expect: bool
    """
    if expect:
        return unittest.expectedFailure
    else:
        return lambda orig: orig


def allowed_failure(func):
    """
    Unit test decorator to allow failure.

    Test runners each have different interpretations of what should be
    the result of an @expectedFailure test if it succeeds.  Some consider
    it to be a pass; others a failure.

    This decorator runs the test and, if it is a failure, reports the result
    and considers it a skipped test.
    """
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except AssertionError:
            tb = traceback.extract_tb(sys.exc_info()[2])
            for depth, line in enumerate(tb):
                if re.match('^assert[A-Z]', line[2]):
                    break
            tb = traceback.format_list(tb[:depth])
            pywikibot.error('\n' + ''.join(tb)[:-1])  # remove \n at the end
            raise unittest.SkipTest('Test is allowed to fail.')
        except Exception:
            pywikibot.exception(tb=True)
            raise unittest.SkipTest('Test is allowed to fail.')
    wrapper.__name__ = func.__name__
    return wrapper


def allowed_failure_if(expect):
    """
    Unit test decorator to allow failure under conditions.

    @param expect: Flag to check if failure is allowed
    @type expect: bool
    """
    if expect:
        return allowed_failure
    else:
        return lambda orig: orig


def add_metaclass(cls):
    """Call six's add_metaclass with the site's __metaclass__ in Python 3."""
    if sys.version_info[0] > 2:
        return six.add_metaclass(cls.__metaclass__)(cls)
    else:
        assert cls.__metaclass__
        return cls


def fixed_generator(iterable):
    """Return a dummy generator ignoring all parameters."""
    def gen(*args, **kwargs):
        for item in iterable:
            yield item

    return gen


class DryParamInfo(dict):

    """Dummy class to use instead of L{pywikibot.data.api.ParamInfo}."""

    def __init__(self, *args, **kwargs):
        """Constructor."""
        super(DryParamInfo, self).__init__(*args, **kwargs)
        self.modules = set()
        self.action_modules = set()
        self.query_modules = set()
        self.query_modules_with_limits = set()
        self.prefixes = set()

    def fetch(self, modules, _init=False):
        """Prevented method."""
        raise Exception(u'DryParamInfo.fetch(%r, %r) prevented'
                        % (modules, _init))

    def parameter(self, module, param_name):
        """Load dry data."""
        return self[module][param_name]


class DummySiteinfo():

    """Dummy class to use instead of L{pywikibot.site.Siteinfo}."""

    def __init__(self, cache):
        """Constructor."""
        self._cache = dict((key, (item, False)) for key, item in cache.items())

    def __getitem__(self, key):
        """Get item."""
        return self.get(key, False)

    def __setitem__(self, key, value):
        """Set item."""
        self._cache[key] = (value, False)

    def get(self, key, get_default=True, cache=True, expiry=False):
        """Return dry data."""
        # Default values are always expired, so only expiry=False doesn't force
        # a reload
        force = expiry is not False
        if not force and key in self._cache:
            loaded = self._cache[key]
            if not loaded[1] and not get_default:
                raise KeyError(key)
            else:
                return loaded[0]
        elif get_default:
            default = pywikibot.site.Siteinfo._get_default(key)
            if cache:
                self._cache[key] = (default, False)
            return default
        else:
            raise KeyError(key)

    def __contains__(self, key):
        """Return False."""
        return False

    def is_recognised(self, key):
        """Return None."""
        return None

    def get_requested_time(self, key):
        """Return False."""
        return False


class DryRequest(CachedRequest):

    """Dummy class to use instead of L{pywikibot.data.api.Request}."""

    def __init__(self, *args, **kwargs):
        """Constructor."""
        _original_Request.__init__(self, *args, **kwargs)

    @classmethod
    def create_simple(cls, **kwargs):
        """Skip CachedRequest implementation."""
        return _original_Request.create_simple(**kwargs)

    def _expired(self, dt):
        """Never invalidate cached data."""
        return False

    def _write_cache(self, data):
        """Never write data."""
        return

    def submit(self):
        """Prevented method."""
        raise Exception(u'DryRequest rejecting request: %r'
                        % self._params)


class DrySite(pywikibot.site.APISite):

    """Dummy class to use instead of L{pywikibot.site.APISite}."""

    _loginstatus = pywikibot.site.LoginStatus.NOT_ATTEMPTED

    def __init__(self, code, fam, user, sysop):
        """Constructor."""
        super(DrySite, self).__init__(code, fam, user, sysop)
        self._userinfo = pywikibot.tools.EMPTY_DEFAULT
        self._paraminfo = DryParamInfo()
        self._siteinfo = DummySiteinfo({})
        self._siteinfo._cache['lang'] = (code, True)
        self._siteinfo._cache['case'] = (
            'case-sensitive' if self.family.name == 'wiktionary' else
            'first-letter', True)
        extensions = []
        if self.family.name == 'wikisource':
            extensions.append({'name': 'ProofreadPage'})
        self._siteinfo._cache['extensions'] = (extensions, True)

    def _build_namespaces(self):
        return Namespace.builtin_namespaces(case=self.siteinfo['case'])

    def __repr__(self):
        """Override default so warnings and errors indicate test is dry."""
        return "%s(%r, %r)" % (self.__class__.__name__,
                               self.code,
                               self.family.name)

    @property
    def userinfo(self):
        """Return dry data."""
        return self._userinfo

    def version(self):
        """Dummy version, with warning to show the callers context."""
        warn('%r returning version 1.24; override if unsuitable.'
             % self, DrySiteNote, stacklevel=2)
        return '1.24'

    def image_repository(self):
        """Return Site object for image repository e.g. commons."""
        code, fam = self.shared_image_repository()
        if bool(code or fam):
            return pywikibot.Site(code, fam, self.username(),
                                  interface=self.__class__)

    def data_repository(self):
        """Return Site object for data repository e.g. Wikidata."""
        code, fam = self.shared_data_repository()
        if bool(code or fam):
            return pywikibot.Site(code, fam, self.username(),
                                  interface=DryDataSite)


class DryDataSite(DrySite, pywikibot.site.DataSite):

    """Dummy class to use instead of L{pywikibot.site.DataSite}."""

    def _build_namespaces(self):
        namespaces = super(DryDataSite, self)._build_namespaces()
        namespaces[0].defaultcontentmodel = 'wikibase-item'
        namespaces[120] = Namespace(id=120,
                                    case='first-letter',
                                    canonical_name='Property',
                                    defaultcontentmodel='wikibase-property')
        return namespaces


class DryPage(pywikibot.Page):

    """Dummy class that acts like a Page but avoids network activity."""

    _pageid = 1
    _disambig = False
    _isredir = False

    def isDisambig(self):
        """Return disambig status stored in _disambig."""
        return self._disambig


class FakeLoginManager(pywikibot.data.api.LoginManager):

    """Loads a fake password."""

    @property
    def password(self):
        """Get the fake password."""
        return 'foo'

    @password.setter
    def password(self, value):
        """Ignore password changes."""
        pass


class DummyHttp(object):

    """A class simulating the http module."""

    def __init__(self, wrapper):
        """Constructor with the given PatchedHttp instance."""
        self.__wrapper = wrapper

    def request(self, *args, **kwargs):
        """The patched request method."""
        result = self.__wrapper.before_request(*args, **kwargs)
        if result is False:
            result = self.__wrapper._old_http.request(*args, **kwargs)
        elif isinstance(result, Mapping):
            result = json.dumps(result)
        elif not isinstance(result, unicode):
            raise ValueError('The result is not a valid type '
                             '"{0}"'.format(type(result)))
        response = self.__wrapper.after_request(result, *args, **kwargs)
        if response is None:
            response = result
        return response

    def fetch(self, *args, **kwargs):
        """The patched fetch method."""
        result = self.__wrapper.before_fetch(*args, **kwargs)
        if result is False:
            result = self.__wrapper._old_http.fetch(*args, **kwargs)
        elif not isinstance(result, threadedhttp.HttpRequest):
            raise ValueError('The result is not a valid type '
                             '"{0}"'.format(type(result)))
        response = self.__wrapper.after_fetch(result, *args, **kwargs)
        if response is None:
            response = result
        return response


class PatchedHttp(object):

    """
    A ContextWrapper to handle any data going through the http module.

    This patches the C{http} import in the given module to a class simulating
    C{request} and C{fetch}. It has a C{data} attribute which is either a
    static value which the requests will return or it's a callable returning the
    data. If it's a callable it'll be called with the same parameters as the
    original function in the L{http} module. For fine grained control it's
    possible to override/monkey patch the C{before_request} and C{before_fetch}
    methods. By default they just return C{data} directory or call it if it's
    callable.

    Even though L{http.request} is calling L{http.fetch}, it won't call the
    patched method.

    The data returned for C{request} may either be C{False}, a C{unicode} or a
    C{Mapping} which is converted into a json string. The data returned for
    C{fetch} can only be C{False} or a L{threadedhttp.HttpRequest}. For both
    variants any other types are not allowed and if it is False it'll use the
    original method and do an actual request.

    Afterwards it is always calling C{after_request} or C{after_fetch} with the
    response and given arguments. That can return a different response too, but
    can also return None so that the original response is forwarded.
    """

    def __init__(self, module, data=None):
        """
        Constructor.

        @param module: The given module to patch. It must have the http module
            imported as http.
        @type module: Module
        @param data: The data returned for any request or fetch.
        @type data: callable or False (or other depending on request/fetch)
        """
        super(PatchedHttp, self).__init__()
        self._module = module
        self.data = data

    def _handle_data(self, *args, **kwargs):
        """Return the data after it may have been called."""
        if self.data is None:
            raise ValueError('No handler is defined.')
        elif callable(self.data):
            return self.data(*args, **kwargs)
        else:
            return self.data

    def before_request(self, *args, **kwargs):
        """Return the value which should is returned by request."""
        return self._handle_data(*args, **kwargs)

    def before_fetch(self, *args, **kwargs):
        """Return the value which should is returned by fetch."""
        return self._handle_data(*args, **kwargs)

    def after_request(self, response, *args, **kwargs):
        """Handle the response after request."""
        pass

    def after_fetch(self, response, *args, **kwargs):
        """Handle the response after fetch."""
        pass

    def __enter__(self):
        """Patch the http module property."""
        self._old_http = self._module.http
        self._module.http = DummyHttp(self)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Reset the http module property."""
        self._module.http = self._old_http


def execute(command, data_in=None, timeout=0, error=None):
    """
    Execute a command and capture outputs.

    @param command: executable to run and arguments to use
    @type command: list of unicode
    """
    # Any environment variables added on Windows must be of type
    # str() on Python 2.
    env = os.environ.copy()

    # Prevent output by test package; e.g. 'max_retries reduced from x to y'
    env[str('PYWIKIBOT_TEST_QUIET')] = str('1')

    # sys.path may have been modified by the test runner to load dependencies.
    pythonpath = os.pathsep.join(sys.path)
    if sys.platform == 'win32' and sys.version_info[0] < 3:
        pythonpath = str(pythonpath)
    env[str('PYTHONPATH')] = pythonpath
    env[str('PYTHONIOENCODING')] = str(config.console_encoding)

    # LC_ALL is used by i18n.input as an alternative for userinterface_lang
    if pywikibot.config.userinterface_lang:
        env[str('LC_ALL')] = str(pywikibot.config.userinterface_lang)

    # Set EDITOR to an executable that ignores all arguments and does nothing.
    env[str('EDITOR')] = str('call' if sys.platform == 'win32' else 'true')

    options = {
        'stdout': subprocess.PIPE,
        'stderr': subprocess.PIPE
    }
    if data_in is not None:
        options['stdin'] = subprocess.PIPE

    try:
        p = subprocess.Popen(command, env=env, **options)
    except TypeError:
        # Generate a more informative error
        if sys.platform == 'win32' and sys.version_info[0] < 3:
            unicode_env = [(k, v) for k, v in os.environ.items()
                           if not isinstance(k, str) or
                           not isinstance(v, str)]
            if unicode_env:
                raise TypeError('os.environ must contain only str: %r'
                                % unicode_env)
            child_unicode_env = [(k, v) for k, v in env.items()
                                 if not isinstance(k, str) or
                                 not isinstance(v, str)]
            if child_unicode_env:
                raise TypeError('os.environ must contain only str: %r'
                                % child_unicode_env)
        raise

    if data_in is not None:
        p.stdin.write(data_in.encode(config.console_encoding))
        p.stdin.flush()  # _communicate() otherwise has a broken pipe

    stderr_lines = b''
    waited = 0
    while (error or (waited < timeout)) and p.poll() is None:
        # In order to kill 'shell' and others early, read only a single
        # line per second, and kill the process as soon as the expected
        # output has been seen.
        # Additional lines will be collected later with p.communicate()
        if error:
            line = p.stderr.readline()
            stderr_lines += line
            if error in line.decode(config.console_encoding):
                break
        time.sleep(1)
        waited += 1

    if (timeout or error) and p.poll() is None:
        p.kill()

    if p.poll() is not None:
        stderr_lines += p.stderr.read()

    data_out = p.communicate()
    return {'exit_code': p.returncode,
            'stdout': data_out[0].decode(config.console_encoding),
            'stderr': (stderr_lines + data_out[1]).decode(config.console_encoding)}


def execute_pwb(args, data_in=None, timeout=0, error=None, overrides=None):
    """
    Execute the pwb.py script and capture outputs.

    @param args: list of arguments for pwb.py
    @type args: list of unicode
    @param overrides: mapping of pywikibot symbols to test replacements
    @type overrides: dict
    """
    command = [sys.executable]

    if sys.version_info < (2, 7, 9):
        # Used to ignore a requests warning
        command.append('-W ignore:A true')

    if overrides:
        command.append('-c')
        overrides = '; '.join(
            '%s = %s' % (key, value) for key, value in overrides.items())
        command.append(
            'import pwb; import pywikibot; %s; pwb.main()'
            % overrides)
    else:
        command.append(_pwb_py)

    return execute(command=command + args,
                   data_in=data_in, timeout=timeout, error=error)
