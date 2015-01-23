"""Test for the load_site method in pywikibot/__init__.py."""

import sys

from pywikibot.site_detect import MWSite

from tests.aspects import unittest, TestCase

if sys.version_info[0] > 2:
    basestring = (str,)


class TestWikiSiteDetection(TestCase):

    """Test Case for MediaWiki detection and site object creation."""

    family = 'meta'
    code = 'meta'
    net = True

    def setUp(self):
        """Set up test."""
        self.failures = {}
        self.errors = {}
        self.pass_no = 0
        self.total = 0
        super(TestWikiSiteDetection, self).setUp()

    def tearDown(self):
        """Tear Down test."""
        super(TestWikiSiteDetection, self).tearDown()
        print('Out of %d sites, %d tests passed, %d tests failed '
              'and %d tests raised an error'
              % (self.total, self.pass_no, len(self.failures), len(self.errors)
                 )
              )
        if self.failures or self.errors:
            print('Failures:\n' + '\n'.join('%s : %s'
                  % (key, value) for (key, value) in self.failures.items()))
            print('Errors:\n' + '\n'.join('%s : %s'
                  % (key, value) for (key, value) in self.errors.items()))

    def assertSite(self, url):
        self._wiki_detection(url, MWSite)

    def assertNoSite(self, url):
        self._wiki_detection(url, None)

    def test_IWM(self):
        """Test the load_site method for MW sites on the IWM list."""
        data = self.get_site().siteinfo['interwikimap']
        for item in data:
            if 'local' not in item:
                self.total += 1
                try:
                    site = MWSite(item['url'])
                except Exception as error:
                    self.errors[item['url']] = error
                    continue
                if type(site) is MWSite:
                    try:
                        version = site.version
                    except Exception as error:
                        self.errors[item['url']] = error
                    else:
                        try:
                            self.assertIsInstance(version, basestring)
                            self.assertRegex(version, r'^\d\.\d+.*')
                            self.pass_no += 1
                        except AssertionError as error:
                            self.failures[item['url']] = error

    def test_detect_site(self):
        """Test detection of MediaWiki sites."""
        self.assertSite('http://botwiki.sno.cc/wiki/$1')
        self.assertSite(
            'http://glossary.reuters.com/index.php?title=Main_Page')
        self.assertSite('http://www.livepedia.gr/index.php?title=$1')
        self.assertSite('http://guildwars.wikia.com/wiki/$1')
        self.assertSite('http://www.gutenberg.org/wiki/$1')
        self.assertSite('http://www.hrwiki.org/index.php/$1')
        self.assertSite('http://seattlewiki.org/wiki/$1')
        self.assertSite('http://wiki.rennkuckuck.de/index.php/$1')
        self.assertSite('http://www.proofwiki.org/wiki/$1')
        self.assertSite('http://wiki.rennkuckuck.de/index.php/$1')
        self.assertSite('http://www.gutenberg.org/wiki/$1')
        self.assertSite(
            'http://www.ck-wissen.de/ckwiki/index.php?title=$1')
        self.assertSite('http://en.citizendium.org/wiki/$1')
        self.assertSite(
            'http://www.lojban.org/tiki/tiki-index.php?page=$1')

    def test_detect_nosite(self):
        """Test detection of non-wiki sites."""
        self.assertNoSite('http://bluwiki.com/go/$1')
        self.assertNoSite('http://www.imdb.com/name/nm$1/')
        self.assertNoSite('http://www.ecyrd.com/JSPWiki/Wiki.jsp?page=$1')
        self.assertNoSite('http://operawiki.info/$1')
        self.assertNoSite(
            'http://www.tvtropes.org/pmwiki/pmwiki.php/Main/$1')
        self.assertNoSite('http://c2.com/cgi/wiki?$1')
        self.assertNoSite('https://phabricator.wikimedia.org/$1')
        self.assertNoSite(
            'http://www.merriam-webster.com/cgi-bin/dictionary?book=Dictionary&va=$1')
        self.assertNoSite('http://arxiv.org/abs/$1')

    def _wiki_detection(self, url, result):
        """Perform one load test."""
        self.total += 1
        try:
            site = MWSite(url)
        except Exception as e:
            print('failed on ' + url)
            self.errors[url] = e
            return
        try:
            if result:
                self.assertIsInstance(site, result)
                self.pass_no += 1
            else:
                self.assertEqual(site, result)
                self.pass_no += 1
        except AssertionError as error:
            self.failures[url] = error


if __name__ == '__main__':
    unittest.main()
