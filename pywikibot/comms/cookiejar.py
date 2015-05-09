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

    """HTTP Cookiejar with multiple session support."""

    vary_key = 'vary-user'
    default_session = 'default'

    def __init__(self, *args, **kwargs):
        """Constructor."""
        self._sessions = defaultdict(dict)
        self._current_session = self.default_session
        LWPCookieJar.__init__(self, *args, **kwargs)

    @property
    def _cookies(self):
        """Get the cookie dict for the current session."""
        self._cookies_lock.acquire()
        try:
            return self._sessions[self._current_session]
        finally:
            self._cookies_lock.release()

    @_cookies.setter
    def _cookies(self, value):
        """Set the cookie dict for the current session."""
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

    def add_cookie_header(self, req, sessionid=None):
        """Add necessary cookies to request."""
        self._cookies_lock.acquire()
        try:
            self._current_session = sessionid or self.default_session
            LWPCookieJar.add_cookie_header(self, req)
        finally:
            self._cookies_lock.release()

    def extract_cookies(self, req, res, sessionid=None):
        """Extract cookies from response."""
        self._cookies_lock.acquire()
        try:
            self._current_session = sessionid or self.default_session
            LWPCookieJar.extract_cookies(self, req, res)
        finally:
            self._cookies_lock.release()
