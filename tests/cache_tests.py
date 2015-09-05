# -*- coding: utf-8  -*-
"""API Request cache tests."""
#
# (C) Pywikibot team, 2014-2015
#
# Distributed under the terms of the MIT license.
#
from __future__ import unicode_literals

__version__ = '$Id$'
#

from pywikibot.enums import enum, LoginStatus, _SimpleEnum
from pywikibot.site import BaseSite

import scripts.maintenance.cache as cache

from tests import _cache_dir
from tests.aspects import unittest, TestCase


class FakeLoginStatus(_SimpleEnum):

    """Fake enum for testing."""

    NOT_ATTEMPTED = -3
    IN_PROGRESS = -2
    NOT_LOGGED_IN = -1
    AS_USER = 0
    AS_SYSOP = 1


class TestLoginStatusEnum(TestCase):

    """Test cases for LoginStatus class."""

    net = False

    def test_fake_repr_result(self):
        """Test fake enum repr."""
        expect = 'FakeLoginStatus(AS_USER)'
        fake = FakeLoginStatus(FakeLoginStatus.AS_USER)

        self.assertEqual(repr(fake), expect)

    def test_enum_repr_result(self):
        """Test enum repr."""
        if not enum:
            raise unittest.SkipTest('enum not available.')
        expect = '<LoginStatus.AS_USER: 0>'

        self.assertEqual(repr(LoginStatus.AS_USER), expect)

        real = LoginStatus(LoginStatus.AS_USER)
        self.assertEqual(repr(real), expect)


class TestLoginStatusParse(TestCase):

    """Test cases for parsing LoginStatus class."""

    net = False

    def test_parse_fake_repr(self):
        """Test old LoginStatus fake repr stored in the cache."""
        parsed = LoginStatus._parse_repr('LoginStatus(AS_USER)')
        self.assertEqual(parsed[0], LoginStatus.AS_USER)
        self.assertEqual(parsed[1], 'LoginStatus(AS_USER)')

    def test_parse_enum_repr(self):
        """Test LoginStatus enum repr."""
        expect = '<LoginStatus.AS_USER: 0>'

        parsed = LoginStatus._parse_repr(expect)
        self.assertEqual(parsed[0], LoginStatus.AS_USER)
        self.assertEqual(parsed[1], expect)

    def test_parse_repr_wrong_start(self):
        """Test missing LoginStatus at start."""
        self.assertRaises(RuntimeError, LoginStatus._parse_repr, 'foo')
        self.assertRaises(RuntimeError,
                          LoginStatus._parse_repr, 'foo<LoginStatus: >')

    def test_parse_repr_wrong_end(self):
        """Test LoginStatus end not detected."""
        self.assertRaises(ValueError,
                          LoginStatus._parse_repr, '<LoginStatus.: ')

    def test_parse_repr_unknown(self):
        """Test unknown LoginStatus."""
        self.assertRaises(KeyError,
                          LoginStatus._parse_repr, '<LoginStatus.BLAH: 0>')


class TestCacheKey(TestCase):

    """Test cases for cache keys."""

    net = False

    def test_site_and_params(self):
        """Test old cache entry key with only Site() and params."""
        entry = cache.CacheEntry('dummy', 'dummy')
        entry.key = "Site(wikipedia:en)[('foo'), ('bar')]"
        (site, username, login_status, params) = entry.parse_key()
        self.assertEqual(site, 'APISite(wikipedia:en)')
        self.assertIsNone(username)
        self.assertIsNone(login_status)
        self.assertEqual(params, "[('foo'), ('bar')]")

    def test_site_old_user_and_params(self):
        """Test cache entry key with only Site(), old User() and params."""
        entry = cache.CacheEntry('dummy', 'dummy')
        entry.key = "Site(wikipedia:en)User(User:abc)[('foo'), ('bar')]"
        (site, username, login_status, params) = entry.parse_key()
        self.assertEqual(site, 'APISite(wikipedia:en)')
        self.assertEqual(username, 'abc')
        self.assertIsNone(login_status)
        self.assertEqual(params, "[('foo'), ('bar')]")

    def test_site_user_and_params(self):
        """Test cache entry key with only Site(), User() and params."""
        entry = cache.CacheEntry('dummy', 'dummy')
        entry.key = "Site(wikipedia:en)User(abc)[('foo'), ('bar')]"
        (site, username, login_status, params) = entry.parse_key()
        self.assertEqual(site, 'APISite(wikipedia:en)')
        self.assertEqual(username, 'abc')
        self.assertIsNone(login_status)
        self.assertEqual(params, "[('foo'), ('bar')]")

    def test_site_loginstatus_and_params(self):
        """Test cache entry key with only Site(), LoginStatus() and params."""
        entry = cache.CacheEntry('dummy', 'dummy')
        entry.key = "Site(wikipedia:en)LoginStatus(NOT_LOGGED_IN)[('foo')]"
        (site, username, login_status, params) = entry.parse_key()
        self.assertEqual(site, 'APISite(wikipedia:en)')
        self.assertIsNone(username)
        self.assertEqual(login_status, LoginStatus.NOT_LOGGED_IN)
        self.assertEqual(params, "[('foo')]")


class RequestCacheTests(TestCase):

    """Validate cache entries."""

    net = False

    def _check_cache_entry(self, entry):
        """Assert validity of the cache entry."""
        self.assertIsInstance(entry.site, BaseSite)
        self.assertIsInstance(entry.site._loginstatus, int)
        self.assertIsInstance(entry.site._username, list)
        if entry.site._loginstatus >= 1:
            self.assertIsNotNone(entry.site._username[0])
        self.assertIsInstance(entry._params, dict)
        self.assertIsNotNone(entry._params)
        # TODO: more tests on entry._params, and possibly fixes needed
        # to make it closely replicate the original object.

    def test_cache(self):
        """Test the apicache by doing _check_cache_entry over each entry."""
        cache.process_entries(_cache_dir, self._check_cache_entry)


if __name__ == '__main__':
    unittest.main()
