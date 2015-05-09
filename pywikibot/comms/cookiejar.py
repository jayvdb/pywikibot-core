# -*- coding: utf-8  -*-
"""HTTP Cookie Jar module."""
from __future__ import unicode_literals

import sys

from collections import defaultdict

if sys.version_info[0] > 2:
    from http.cookiejar import LWPCookieJar, deepvalues
else:
    from cookielib import LWPCookieJar, deepvalues


class MultiSessionLWPCookieJar(LWPCookieJar):

    """
    HTTP Cookiejar with multiple session support.

    Instead of one cookie jar in _cookies, the cookies are stored in
    multiple cookie jars, which are placed in _sessions and are identified
    by a textual session key.

    The current session is held in _current_session.

    The property _cookies switches between sessions so that LWPCookieJar
    operations work as if there is only one cookie jar.

    set_cookie looks for a cookie-attribute defined by vary_key to identify
    which session the cookie is part of.  If that cookie-attribute doesnt exist,
    the current session is used.

    Any LWPCookieJar operation used must be overridden to obtain the session ID
    for that operation.
    """

    vary_key = 'vary-user'
    default_session = 'default'

    def __init__(self, *args, **kwargs):
        """Constructor."""
        self._sessions = defaultdict(dict)
        self._current_session = self.default_session
        LWPCookieJar.__init__(self, *args, **kwargs)
        # In Python 2, the instance variable has higher precedence than
        # the attribute
        if sys.version_info[0] < 3:
            del self._cookies

    @property
    def _cookies(self):
        """Get the cookie jar for the current session."""
        self._cookies_lock.acquire()
        try:
            return self._sessions[self._current_session]
        finally:
            self._cookies_lock.release()

    @_cookies.setter
    def _cookies(self, value):
        """Set the cookie jar for the current session.

        This should only be called once during LWPCookieJar.__init__.
        """
        self._cookies_lock.acquire()
        try:
            self._sessions[self._current_session] = value
        finally:
            self._cookies_lock.release()

    def __iter__(self):
        """Iterate over all cookies in all sessions."""
        return deepvalues(self._sessions)

    def set_cookie(self, cookie):
        """
        Set vary attribute in cookie and then set cookie.

        If vary attribute is in cookie, set the session to its value.
        """
        self._cookies_lock.acquire()
        try:
            if self.vary_key in cookie._rest:
                self._current_session = cookie._rest[self.vary_key]
            else:
                cookie._rest[self.vary_key] = self._current_session

            LWPCookieJar.set_cookie(self, cookie)
        finally:
            self._cookies_lock.release()

    def add_cookie_header(self, request, sessionid=None):
        """Add necessary cookies to request.

        @param sessionid: session identifier
        @type sessionid: str
        """
        self._cookies_lock.acquire()
        try:
            self._current_session = sessionid or self.default_session
            LWPCookieJar.add_cookie_header(self, request)
        finally:
            self._cookies_lock.release()

    def extract_cookies(self, response, request, sessionid=None):
        """Extract cookies from response, where allowable given the request.

        @param sessionid: session identifier
        @type sessionid: str
        """
        self._cookies_lock.acquire()
        try:
            self._current_session = sessionid or self.default_session
            LWPCookieJar.extract_cookies(self, response, request)
        finally:
            self._cookies_lock.release()
