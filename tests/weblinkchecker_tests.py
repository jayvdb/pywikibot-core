# -*- coding: utf-8  -*-
"""weblinkchecker test module."""
#
# (C) Pywikibot team, 2015
#
# Distributed under the terms of the MIT license.
#
from __future__ import absolute_import, unicode_literals

__version__ = '$Id$'

import datetime

from pywikibot.tools import PY2
if not PY2:
    from urllib.parse import urlparse
else:
    from urlparse import urlparse

from scripts import weblinkchecker

from tests.aspects import unittest, TestCase, TestCaseBase
from tests import weblib_tests


class MementoTestBase(TestCaseBase):

    """Test memento client."""

    @classmethod
    def setUpClass(cls):
        """Set up test class."""
        if isinstance(weblinkchecker.memento_client, ImportError):
            raise unittest.SkipTest('memento_client not imported')
        super(MementoTestBase, cls).setUpClass()

    def _get_archive_url(self, url, date_string=None):
        if date_string is None:
            when = datetime.datetime.now()
        else:
            when = datetime.datetime.strptime(date_string, '%Y%m%d')
        return weblinkchecker._get_closest_memento_url(
            url,
            when,
            self.timegate_uri)


class WeblibTestMementoInternetArchive(MementoTestBase, weblib_tests.TestInternetArchive):

    """Test InternetArchive Memento using old weblib tests."""

    timegate_uri = 'http://web.archive.org/web/'
    hostname = timegate_uri


class WeblibTestMementoWebCite(MementoTestBase, weblib_tests.TestWebCite):

    """Test WebCite Memento using old weblib tests."""

    timegate_uri = 'http://timetravel.mementoweb.org/webcite/timegate/'
    hostname = timegate_uri


class TestMementoWebCite(MementoTestBase):

    """New WebCite Memento tests."""

    timegate_uri = 'http://timetravel.mementoweb.org/webcite/timegate/'
    hostname = timegate_uri

    def test_newest(self):
        """Test WebCite for newest https://google.com."""
        archivedversion = self._get_archive_url('https://google.com')
        parsed = urlparse(archivedversion)
        self.assertIn(parsed.scheme, ['http', 'https'])
        self.assertEqual(parsed.netloc, 'www.webcitation.org')


class TestMementoDefault(MementoTestBase, TestCase):

    """Test InternetArchive is default Memento timegate."""

    timegate_uri = None
    net = True

    def test_newest(self):
        """Test getting memento for newest https://google.com."""
        archivedversion = self._get_archive_url('https://google.com')
        self.assertIsNotNone(archivedversion)

    def test_invalid(self):
        """Test getting memento for invalid URL."""
        self.assertRaises(Exception, self._get_archive_url, 'invalid')


if __name__ == '__main__':
    try:
        unittest.main()
    except SystemExit:
        pass
