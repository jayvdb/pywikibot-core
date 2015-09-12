# -*- coding: utf-8  -*-
"""Test confirming paraminfo contains expected values."""
#
# (C) Pywikibot team, 2015
#
# Distributed under the terms of the MIT license.
#
from __future__ import unicode_literals

__version__ = '$Id$'
#

from pywikibot.family import WikimediaFamily
from pywikibot.page import Claim, Property
from pywikibot.tools import MediaWikiVersion

from tests.aspects import (
    unittest,
    TestCaseBase,
    DefaultSiteTestCase,
    DefaultWikibaseClientTestCase,
    WikimediaDefaultSiteTestCase,
)


class KnownTypesTestBase(TestCaseBase):

    """Base class for paraminfo checks."""

    def _get_param_values(self, site, module, parameter):
        """Perform check that a parameter matches the expected list."""
        try:
            param = site._paraminfo.parameter(module, parameter)
        except ValueError:
            raise unittest.SkipTest(
                'Paraminfo for {0} could not be loaded'.format(module))
        if not param or 'type' not in param:
            raise unittest.SkipTest(
                'No defined values for {0}.{1}'.format(module, parameter))
        return param['type']

    def _check_param_values(self, site, module, parameter, expected):
        """Perform check that a parameter matches the expected list."""
        lov = self._get_param_values(site, module, parameter)
        self.assertCountEqual(lov, expected)

    def _check_param_subset(self, site, module, parameter, expected):
        """Perform check that a parameter matches the expected list."""
        lov = self._get_param_values(site, module, parameter)
        for item in expected:
            self.assertIn(item, lov)


class MediaWikiKnownTypesTestCase(KnownTypesTestBase,
                                  DefaultSiteTestCase):

    """Verify MediaWiki types using paraminfo."""

    def test_api_format(self):
        """Test api format."""
        known = ['json', 'xml']
        self._check_param_subset(self.site, 'main', 'format', known)

    def test_assert_user(self):
        """Test assert type."""
        known = ['user', 'bot']
        self._check_param_subset(self.site, 'main', 'assert', known)

    def test_feed_format(self):
        """Test feed format."""
        known = ['rss', 'atom']

        if self.site.has_extension('GoogleNewsSitemap'):
            known.append('sitemap')

        self._check_param_values(
            self.site, 'feedwatchlist', 'feedformat', known)

    def test_watchlist_show_flags(self):
        """Test watchlist show flags."""
        types = ['minor', 'bot', 'anon', 'patrolled']
        if MediaWikiVersion(self.site.version()) >= MediaWikiVersion('1.24'):
            types.append('unread')

        known = types + ['!%s' % item for item in types]

        self._check_param_values(self.site, 'query+watchlist', 'show', known)

    def test_watchlist_type(self):
        """Test watchlist type."""
        known = ['edit', 'external', 'new', 'log']  # 'external' is likely new

        self._check_param_values(self.site, 'query+watchlist', 'type', known)

    def test_watchlist_modification_flag(self):
        """Test watchlist modification flag."""
        known = ['watch', 'unwatch', 'preferences', 'nochange']

        self._check_param_values(self.site, 'edit', 'watchlist', known)
        self._check_param_values(self.site, 'delete', 'watchlist', known)
        self._check_param_values(self.site, 'move', 'watchlist', known)
        self._check_param_values(self.site, 'protect', 'watchlist', known)
        self._check_param_values(self.site, 'rollback', 'watchlist', known)
        self._check_param_values(self.site, 'undelete', 'watchlist', known)

        known = ['watch', 'preferences', 'nochange']
        self._check_param_values(self.site, 'upload', 'watchlist', known)

    def test_content_format(self):
        """Test content format."""
        wmf = ('text/x-wiki',
               'text/javascript',
               'application/json',
               'text/css',
               'text/plain',
               )
        self._check_param_values(self.site, 'edit', 'contentformat', wmf)
        self._check_param_values(self.site, 'parse', 'contentformat', wmf)

    def test_content_model(self):
        """Test content model."""
        base = ('wikitext',
                'javascript',
                'json',
                'css',
                'text',
                )
        self._check_param_subset(self.site, 'edit', 'contentmodel', base)
        self._check_param_subset(self.site, 'parse', 'contentmodel', base)

        if isinstance(self.site.family, WikimediaFamily):
            self._check_param_subset(self.site, 'parse', 'contentmodel', (
                'MassMessageListContent',
                'SecurePoll',
                'flow-board',
                'Scribunto',
                'JsonSchema',
            ))

    def test_revision_deletion_type(self):
        """Test revision deletion type."""
        known = ['revision', 'archive', 'oldimage', 'filearchive', 'logging']

        self._check_param_values(self.site, 'revisiondelete', 'type', known)

    def test_revision_deletion_what(self):
        """Test revision deletion part."""
        known = ['content', 'comment', 'user']

        self._check_param_values(self.site, 'revisiondelete', 'hide', known)

    def test_revision_deletion_level(self):
        """Test revision deletion level."""
        known = ['yes', 'no', 'nochange']

        self._check_param_values(
            self.site, 'revisiondelete', 'suppress', known)


class SiteMatrixKnownTypesTestCase(KnownTypesTestBase,
                                   WikimediaDefaultSiteTestCase):

    """Verify Echo types using paraminfo."""

    def test_site_matrix_type(self):
        """Test site matrix type."""
        known = ['special', 'language']

        self._check_param_values(self.site, 'sitematrix', 'type', known)

    def test_site_matrix_state(self):
        """Test site matrix state."""
        known = ['closed', 'private', 'fishbowl', 'all']

        self._check_param_values(self.site, 'sitematrix', 'state', known)


class EchoKnownTypesTestCase(KnownTypesTestBase,
                             WikimediaDefaultSiteTestCase):

    """Verify Echo types using paraminfo."""

    def test_echo_types(self):
        """Test Echo notification types."""
        known = ['alert', 'message']

        self._check_param_values(self.site, 'echomarkread', 'sections', known)

        known = ['alert', 'message', 'all']

        self._check_param_values(self.site, 'echomarkseen', 'type', known)


class WikibaseKnownTypesTests(KnownTypesTestBase,
                              DefaultWikibaseClientTestCase):

    """Verify Wikibase types using paraminfo."""

    def test_entities(self):
        """Test known entities."""
        known = ['item', 'property']
        self._check_param_values(self.repo, 'wbsearchentities', 'type', known)

    def test_datatypes(self):
        """Test known datatypes."""
        unsupported = set(['monolingualtext', 'wikibase-property'])
        known = set(Property.types) | unsupported
        self._check_param_values(self.repo, 'wbformatvalue', 'datatype', known)

    def test_snaktype(self):
        """Test known snak types."""
        known = Claim.SNAK_TYPES
        self._check_param_values(self.repo, 'wbcreateclaim', 'snaktype', known)

    def test_rank(self):
        """Test known ranks."""
        known = ['deprecated', 'normal', 'preferred']
        self._check_param_values(self.repo, 'wbgetclaims', 'rank', known)


if __name__ == '__main__':
    unittest.main()
