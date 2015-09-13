# -*- coding: utf-8  -*-
"""Tests for exceptions."""
#
# (C) Pywikibot team, 2014-2015
#
# Distributed under the terms of the MIT license.
#
from __future__ import unicode_literals

__version__ = '$Id$'

import pywikibot

from pywikibot.data.api import APIError
from pywikibot.exceptions import (
    Error,
    SiteRelatedError,
    PageRelatedError,
    UsernameNotSpecified,
    _SysopnameNotSpecified,
)
from pywikibot.tools import PY2

from tests.aspects import (
    unittest,
    TestCase,
    DefaultSiteTestCase,
    DeprecationTestCase,
)

if not PY2:
    unicode = str


class TestError(TestCase):

    """Test base Error class."""

    net = False

    def test_base(self):
        """Test Error('foo')."""
        exception = Error('foo')
        self.assertEqual(str(exception), 'foo')
        self.assertEqual(unicode(exception), 'foo')
        self.assertEqual(exception.args, ('foo', ))
        self.assertEqual(exception.message, 'foo')


class TestSiteRelatedError(DefaultSiteTestCase):

    """Test base Error class."""

    dry = True

    def test_site_related_error_base(self):
        exception = SiteRelatedError(self.site, 'foo')
        self.assertEqual(str(exception), 'foo')
        self.assertEqual(unicode(exception), 'foo')

        self.assertEqual(exception.args, ('foo', ))
        self.assertEqual(exception.message, 'foo')

        self.assertEqual(exception.site, self.site)
        self.assertEqual(exception.family, self.site.family.name)
        self.assertEqual(exception.site_code, self.site.code)

    def test_site_related_error_percent(self):
        exception = SiteRelatedError(self.site, 'foo %s bar')
        expect = 'foo %s bar' % self.site
        self.assertEqual(str(exception), expect)
        self.assertEqual(unicode(exception), expect)

        self.assertEqual(exception.args, (expect, ))
        self.assertEqual(exception.message, 'foo %s bar')

        self.assertEqual(exception.site, self.site)
        self.assertEqual(exception.family, self.site.family.name)
        self.assertEqual(exception.site_code, self.site.code)

    def test_site_related_error_percent_dict(self):
        exception = SiteRelatedError(self.site, 'foo %(site)s bar')
        expect = 'foo %s bar' % self.site
        self.assertEqual(str(exception), expect)
        self.assertEqual(unicode(exception), expect)

        self.assertEqual(exception.args, (expect, ))
        self.assertEqual(exception.message, 'foo %(site)s bar')

        self.assertEqual(exception.site, self.site)
        self.assertEqual(exception.family, self.site.family.name)
        self.assertEqual(exception.site_code, self.site.code)


class TestPageRelatedError(DefaultSiteTestCase):

    """Test base Error class."""

    dry = True

    def test_page_related_error_base(self):
        mainpage = self.get_mainpage()
        exception = PageRelatedError(mainpage, 'foo')

        self.assertEqual(str(exception), 'foo')
        self.assertEqual(unicode(exception), 'foo')

        self.assertEqual(exception.args, ('foo', ))
        self.assertEqual(exception.message, 'foo')

        self.assertEqual(exception.site, self.site)

    def test_page_related_error_percent(self):
        mainpage = self.get_mainpage()
        exception = PageRelatedError(mainpage, 'foo %s bar')
        expect = 'foo %s bar' % mainpage

        self.assertEqual(str(exception), expect)
        self.assertEqual(unicode(exception), expect)

        self.assertEqual(exception.args, (expect, ))
        self.assertEqual(exception.message, expect)

        self.assertEqual(exception.site, self.site)

    def test_page_related_error_percent_dict_page(self):
        mainpage = self.get_mainpage()
        exception = PageRelatedError(mainpage, 'foo %(site)s %(page)s bar')
        expect = 'foo %s %s bar' % (self.site, mainpage)

        self.assertEqual(str(exception), expect)
        self.assertEqual(unicode(exception), expect)

        self.assertEqual(exception.args, (expect, ))
        self.assertEqual(exception.message, 'foo %(site)s %(page)s bar')

        self.assertEqual(exception.site, self.site)

    def test_page_related_error_percent_dict_title(self):
        mainpage = self.get_mainpage()
        exception = PageRelatedError(mainpage, 'foo %(site)s %(title)s bar')
        expect = 'foo %s %s bar' % (self.site, mainpage.title(asLink=True))

        self.assertEqual(str(exception), expect)
        self.assertEqual(unicode(exception), expect)

        self.assertEqual(exception.args, (expect, ))
        self.assertEqual(exception.message, 'foo %(site)s %(title)s bar')

        self.assertEqual(exception.site, self.site)


class TestUsernameExceptions(DefaultSiteTestCase):

    """Test cases for username exceptions."""

    dry = True

    def test_username_not_specified(self):
        """Test message of UsernameNotSpecified."""
        exception = UsernameNotSpecified(self.site)
        self.assertIn(
            "usernames['{0}']['{1}'] = 'myUsername'".format(
                self.site.family.name, self.site.code),
            str(exception))

    def test_sysopname_not_specified(self):
        """Test message of _SysopnameNotSpecified."""
        exception = _SysopnameNotSpecified(self.site)
        self.assertIn(
            "sysopnames['{0}']['{1}'] = 'myUsername'".format(
                self.site.family.name, self.site.code),
            str(exception))


class TestDeprecatedExceptions(DeprecationTestCase, DefaultSiteTestCase):

    """Test usage of deprecation in library code."""

    dry = False

    def test_UploadWarning(self):
        """Test exceptions.UploadWarning is deprecated only."""
        # Accessing from the main package should work fine.
        cls = pywikibot.UploadWarning
        self.assertNoDeprecation()
        e = cls('foo', 'bar', site=self.site)
        self.assertIsInstance(e, pywikibot.Error)
        self.assertNoDeprecation()

        self._reset_messages()

        # But it sholdnt be accessed from the exceptions module.
        cls = pywikibot.exceptions.UploadWarning

        self.assertOneDeprecationParts('pywikibot.exceptions.UploadWarning',
                                       'pywikibot.data.api.UploadWarning')

        e = cls('foo', 'bar', site=self.site)
        self.assertIsInstance(e, pywikibot.Error)
        self.assertNoDeprecation()

    def test_PageNotFound(self):
        """Test PageNotFound is deprecated from the package."""
        cls = pywikibot.PageNotFound
        self.assertOneDeprecation(
            'pywikibot.PageNotFound is deprecated, and no longer '
            'used by pywikibot; use http.fetch() instead.')

        e = cls('foo')
        self.assertIsInstance(e, pywikibot.Error)
        self.assertOneDeprecationParts(
            'pywikibot.exceptions.DeprecatedPageNotFoundError')

        cls = pywikibot.exceptions.PageNotFound

        self.assertOneDeprecation(
            'pywikibot.exceptions.PageNotFound is deprecated, and no longer '
            'used by pywikibot; use http.fetch() instead.')

        e = cls('foo')
        self.assertIsInstance(e, pywikibot.Error)
        self.assertOneDeprecationParts(
            'pywikibot.exceptions.DeprecatedPageNotFoundError')


class TestAPIError(DefaultSiteTestCase):

    """Test base APIError class."""

    dry = True

    def test_base(self):
        exception = APIError('foo-code', 'foo-message', self.site)
        self.assertEqual(str(exception), 'foo-code: foo-message')
        self.assertEqual(unicode(exception), 'foo-code: foo-message')

        self.assertEqual(exception.args, ('foo-code: foo-message', ))
        self.assertEqual(exception.message, 'foo-code: foo-message')

        self.assertEqual(exception.site, self.site)
        self.assertEqual(exception.family, self.site.family.name)
        self.assertEqual(exception.site_code, self.site.code)


if __name__ == '__main__':
    try:
        unittest.main()
    except SystemExit:
        pass
