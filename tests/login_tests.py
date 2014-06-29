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


class UnCachedTestSiteLoginObject(DefaultSiteTestCase):

    """Test cases for uncached Site login methods."""

    cached = False
    user = True

    def test_user(self):
        """Test site.login(sysop=False) method."""
        self.site.login(sysop=False)
        self.assertEquals(self.site._loginstatus, LoginStatus.AS_USER)
        self.assertTrue(self.site.logged_in(sysop=False))
        self.assertFalse(self.site.logged_in(sysop=True))
        self.site.logout()
        self.assertEquals(self.site._loginstatus, LoginStatus.NOT_LOGGED_IN)

    def test_sysop(self):
        """Test site.login(sysop=True) method."""
        if not self.site._username[True]:
            raise self.skipTest('no sysopname for %s' % self.site)

        self.site.login(sysop=True)
        self.assertTrue(self.site.logged_in(sysop=True))
        self.assertFalse(self.site.logged_in(sysop=False))
        self.assertEquals(self.site._loginstatus, LoginStatus.AS_SYSOP)


class CachedTestSiteLoginObject(DefaultSiteTestCase):

    """Simple test cases for cached Site login methods."""

    cached = True
    user = True

    def test_user(self):
        """Test site.login(sysop=False) method."""
        self.site.login(sysop=False)
        self.assertEqual(self.site._loginstatus, LoginStatus.AS_USER)
        self.assertTrue(self.site.logged_in(sysop=False))
        self.assertFalse(self.site.logged_in(sysop=True))
        self.site.logout()
        self.assertEqual(self.site._loginstatus, LoginStatus.NOT_LOGGED_IN)

    def test_sysop(self):
        """Test site.login(sysop=True) method."""
        if not self.site._username[True]:
            raise self.skipTest('no sysopname for %s' % self.site)

        self.site.login(sysop=True)
        self.assertEquals(self.site._loginstatus, LoginStatus.AS_SYSOP)
        self.assertTrue(self.site.logged_in(sysop=True))
        self.assertFalse(self.site.logged_in(sysop=False))

    def test_user_no_sysop(self):
        """Test site.login(sysop=True) method when no sysopname is present."""
        if self.site._username[True]:
            raise self.skipTest(
                'Cant test for fallback on %s as a sysopname is present'
                % self.site)

        self.site.login(sysop=False)
        self.assertTrue(self.site.logged_in(sysop=False))
        self.assertEqual(self.site._loginstatus, LoginStatus.AS_USER)

        self.assertRaises(NoUsername, self.site.login, sysop=True)
        self.assertEqual(self.site._loginstatus, LoginStatus.AS_USER)
        self.assertTrue(self.site.logged_in(sysop=False))
        self.assertFalse(self.site.logged_in(sysop=True))


if __name__ == '__main__':
    try:
        unittest.main()
    except SystemExit:
        pass
