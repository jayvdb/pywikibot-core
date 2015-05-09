# -*- coding: utf-8  -*-
"""HTTP Cookie Jar module."""
from __future__ import unicode_literals

import sys

if sys.version_info[0] > 2:
    from http.cookiejar import LWPCookieJar, deepvalues
else:
    from cookielib import LWPCookieJar, deepvalues


class MultiSessionLWPCookieJar(LWPCookieJar):

    """HTTP Cookiejar with multiple session support."""

    vary_key = 'vary-user'

    def __init__(self, *args, **kwargs):
        """Constructor."""
        LWPCookieJar.__init__(self, *args, **kwargs)
        self._sessions = {'default': {}}
        self._current_session = 'default'
        self._cookies = self._sessions['default']

    def _set_current_session(self, value):
        """Set session ID.

        Note this is not thread-safe
        """
        if value is None:
            value = 'default'
        if self._current_session == value:
            return
        self._cookies_lock.acquire()
        try:
            self._sessions[self._current_session] = self._cookies

            self._cookies = self._sessions.setdefault(value, {})
            self._current_session = value
        finally:
            self._cookies_lock.release()

    def __iter__(self):
        return deepvalues(self._sessions)

    def set_cookie(self, cookie):
        """
        Set vary attribute in cookie and then set cookie.

        If vary attribute is in cookie, set the session to its value.
        """
        self._cookies_lock.acquire()
        try:
            if self.vary_key in cookie._rest:
                self._set_current_session(cookie._rest[self.vary_key])
            else:
                cookie._rest[self.vary_key] = self._current_session

            LWPCookieJar.set_cookie(self, cookie)
        finally:
            self._cookies_lock.release()

    def add_cookie_header(self, req, sessionid=None):
        """Add necessary cookies to request."""
        self._cookies_lock.acquire()
        try:
            self._set_current_session(sessionid)
            LWPCookieJar.add_cookie_header(self, req)
        finally:
            self._cookies_lock.release()

    def extract_cookies(self, req, res, sessionid=None):
        """Extract cookies from response."""
        self._cookies_lock.acquire()
        try:
            self._set_current_session(sessionid)
            LWPCookieJar.extract_cookies(self, req, res)
        finally:
            self._cookies_lock.release()
