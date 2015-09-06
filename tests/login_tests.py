# -*- coding: utf-8  -*-
"""Tests for the login sequence."""
#
# (C) Pywikibot team, 2015
#
# Distributed under the terms of the MIT license.
#
from __future__ import unicode_literals

__version__ = '$Id$'


from pywikibot.exceptions import NoUsername
from pywikibot.site import LoginStatus

from tests.aspects import DefaultSiteTestCase, unittest


class TestSiteLogin(DefaultSiteTestCase):

    """Test cases for Site login methods."""

    cached = False
    user = True

    def test_user(self):
        """Test site.login(sysop=False) method."""
        self.site.login(sysop=False)
        self.assertEqual(self.site._loginstatus, LoginStatus.AS_USER)
        self.assertTrue(self.site.logged_in(sysop=False))

    def test_user_logout(self):
        """Test site.logout method."""
        if self.site.is_oauth_token_available():
            raise unittest.SkipTest('Oauth active; cannot logout')
        self.site.login(sysop=False)
        self.site.logout()
        self.assertEqual(self.site._loginstatus, LoginStatus.NOT_LOGGED_IN)
        self.assertFalse(self.site.logged_in(sysop=False))

    def test_sysop(self):
        """Test site.login(sysop=True) method."""
        if not self.site._username[True]:
            raise self.skipTest('no sysopname for %s' % self.site)
        if self.site._username[True] == self.site._username[False]:
            raise self.skipTest('sysopname for %s is identical to username'
                                % self.site)

        self.site.login(sysop=True)
        self.assertEqual(self.site._loginstatus, LoginStatus.AS_SYSOP)
        self.assertTrue(self.site.logged_in(sysop=True))

    @unittest.expectedFailure
    def test_user_no_sysop(self):
        """Test site.login(sysop=True) method when no sysopname is present."""
        if self.site._username[True]:
            raise self.skipTest(
                'Can not test for fallback on %s as a sysopname is present'
                % self.site)

        self.site.login(sysop=False)
        self.assertEqual(self.site._loginstatus, LoginStatus.AS_USER)
        self.assertTrue(self.site.logged_in(sysop=False))

        self.assertRaises(NoUsername, self.site.login, sysop=True)
        # T100965: after exception; login fails to restore previous state
        self.assertEqual(self.site._loginstatus, LoginStatus.AS_USER)
        self.assertTrue(self.site.logged_in(sysop=False))


class TestCachedSiteLogin(TestSiteLogin, DefaultSiteTestCase):

    """Test cached Site login methods."""

    cached = True
    user = True


if __name__ == '__main__':
    try:
        unittest.main()
    except SystemExit:
        pass
