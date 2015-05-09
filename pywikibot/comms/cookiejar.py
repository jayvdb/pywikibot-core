# -*- coding: utf-8  -*-
"""HTTP Cookie Jar module."""

import sys

if sys.version_info[0] > 2:
    from http import cookiejar as cookielib
else:
    import cookielib


class MultiSessionCookieJar(cookielib.LWPCookieJar):

    """HTTP Cookiejar with multiple session support."""

    vary_key = 'vary-user'

    def __init__(self, *args, **kwargs):
        """Constructor."""
        cookielib.LWPCookieJar.__init__(self, *args, **kwargs)
        self._sessions = {'default': {}}
        self._current_session = 'default'
        self._cookies = self._sessions['default']

    @property
    def current_session(self):
        """Get session ID."""
        return self._current_session

    @current_session.setter
    def current_session(self, value):
        """Set session ID."""
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
        return cookielib.deepvalues(self._sessions)

    def set_cookie(self, cookie):
        """
        Set vary attribute in cookie and then set cookie.

        If vary attribute is in cookie, set the session to its value.
        """
        self._cookies_lock.acquire()
        try:
            if self.vary_key in cookie._rest:
                self.current_session = cookie._rest[self.vary_key]
            else:
                cookie._rest[self.vary_key] = self._current_session

            cookielib.LWPCookieJar.set_cookie(self, cookie)
        finally:
            self._cookies_lock.release()


class MultiSessionLWPCookieJar(MultiSessionCookieJar,
                               cookielib.LWPCookieJar):

    """HTTP Cookiejar with multiple session support stored in LWP format."""

    pass
