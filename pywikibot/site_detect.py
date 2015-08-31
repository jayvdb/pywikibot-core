# -*- coding: utf-8  -*-
"""Classes for detecting a MediaWiki site."""
#
# (C) Pywikibot team, 2010-2015
#
# Distributed under the terms of the MIT license.
#
from __future__ import unicode_literals

__version__ = '$Id$'
#

import json
import re

from distutils.version import LooseVersion as V

import pywikibot

from pywikibot.comms.http import fetch
from pywikibot.exceptions import ServerError
from pywikibot.tools import PY2, PYTHON_VERSION

if not PY2:
    from html.parser import HTMLParser
    from urllib.parse import urljoin, urlparse
else:
    from HTMLParser import HTMLParser
    from urlparse import urljoin, urlparse


class HTMLRegexDetectSite(object):

    """Detect a site using wg variables in the HTML."""

    REwgEnableApi = re.compile(r'wgEnableAPI ?= ?true')
    REwgServer = re.compile(r'wgServer ?= ?"([^"]*)"')
    REwgScriptPath = re.compile(r'wgScriptPath ?= ?"([^"]*)"')
    REwgArticlePath = re.compile(r'wgArticlePath ?= ?"([^"]*)"')
    REwgContentLanguage = re.compile(r'wgContentLanguage ?= ?"([^"]*)"')
    REwgVersion = re.compile(r'wgVersion ?= ?"([^"]*)"')

    def _parse_pre_117(self, data):
        """Parse HTML."""
        if not self.REwgEnableApi.search(data):
            print("*** WARNING: Api does not seem to be enabled on %s"
                  % self.fromurl)
        try:
            self.version = self.REwgVersion.search(data).groups()[0]
        except AttributeError:
            self.version = None

        self.server = self.REwgServer.search(data).groups()[0]
        self.scriptpath = self.REwgScriptPath.search(data).groups()[0]
        self.articlepath = self.REwgArticlePath.search(data).groups()[0]
        self.lang = self.REwgContentLanguage.search(data).groups()[0]


class MWSite(HTMLRegexDetectSite):

    """Minimal wiki site class."""

    def __init__(self, fromurl):
        """Constructor."""
        self.fromurl = fromurl
        if fromurl.endswith("$1"):
            fromurl = fromurl[:-2]
        r = fetch(fromurl)
        if r.status == 503:
            raise ServerError('Service Unavailable')

        if fromurl != r.data.url:
            print('{0} redirected to {1}'.format(fromurl, r.data.url))
            fromurl = r.data.url

        self.server = None

        data = r.content

        wp = WikiHTMLPageParser(fromurl)
        wp.feed(data)

        self.version = wp.version
        self.server = wp.server
        self.scriptpath = wp.scriptpath

        if wp.server:
            #api_url = urlparse(wp.api_url)
            #self.server = '{0}://{1}'.format(api_url.scheme, api_url.netloc)
            #self.scriptpath = api_url.path

            try:
                self._parse_post_117()
            except Exception as e:
                pywikibot.warning('MW 1.17+ detection failed: {0!r}'.format(e))

        if not self.server or not self.version:
            old_site = HTMLRegexDetectSite()
            self._parse_pre_117(data)
            self._fetch_old_version()

        if not self.version or V(self.version) < V('1.14'):
            raise Exception('Unsupported version: %r' % self.version)

    @property
    def langs(self):
        response = fetch(
            self.api +
            "?action=query&meta=siteinfo&siprop=interwikimap&sifilteriw=local&format=json")
        iw = json.loads(response.content)
        if 'error' in iw:
            raise RuntimeError('%s - %s' % (iw['error']['code'],
                                            iw['error']['info']))
        self.langs = [wiki for wiki in iw['query']['interwikimap']
                      if u'language' in wiki]
        return self.langs

    def _fetch_old_version(self):
        """Extract the version from API help with ?version enabled."""
        if self.version is None:
            try:
                d = json.loads(fetch(self.api + '?version&format=json').content)
                self.version = list(filter(
                    lambda x: x.startswith("MediaWiki"),
                    [l.strip()
                     for l in d['error']['*'].split("\n")]))[0].split()[1]
            except Exception:
                pass

    def _parse_post_117(self):
        response = fetch(self.api + '?action=query&meta=siteinfo&format=json')
        info = json.loads(response.content)['query']['general']
        self.version = info['generator'][10:]
        self.server = urljoin(self.fromurl, info['server'])
        for item in ['scriptpath', 'articlepath', 'lang']:
            setattr(self, item, info[item])

    def __cmp__(self, other):
        return (self.server + self.scriptpath ==
                other.server + other.scriptpath)

    def __hash__(self):
        return hash(self.server + self.scriptpath)

    @property
    def api(self):
        return self.server + self.scriptpath + "/api.php"

    @property
    def iwpath(self):
        return self.server + self.articlepath


class WikiHTMLPageParser(HTMLParser):

    """Wiki HTML page parser."""

    def __init__(self, url):
        """Constructor."""
        if PYTHON_VERSION < (3, 4):
            HTMLParser.__init__(self)
        else:
            super().__init__(convert_charrefs=True)
        self.url = urlparse(url)
        self.generator = None
        self.version = None
        self._parsed_url = None
        self.server = None
        self.scriptpath = None

    def set_version(self, value):
        """Set highest version."""
        if self.version:
            if V(value) < V(self.version):
                return

        self.version = value

    def set_api_url(self, value):
        """Set api_url."""
        new_parsed_url = urlparse(value)
        if not new_parsed_url.scheme or not new_parsed_url.netloc:
            new_parsed_url = urlparse(
                '{0}://{1}{2}'.format(
                    new_parsed_url.scheme or self.url.scheme,
                    new_parsed_url.netloc or self.url.netloc,
                    new_parsed_url.path))

        if self._parsed_url:
            assert self._parsed_url == new_parsed_url, '{0} != {1}'.format(
                self._parsed_url, new_parsed_url)
        else:
            self._parsed_url = new_parsed_url
            self.server = '{0}://{1}'.format(
                self._parsed_url.scheme, self._parsed_url.netloc)
            self.scriptpath = self._parsed_url.path

    def handle_starttag(self, tag, attrs):
        """Handle an opening tag."""
        attrs = dict(attrs)
        if tag == "meta":
            if attrs.get('name') == 'generator':
                self.generator = attrs["content"]
                self.version = self.generator[10:]
        elif tag == 'link':
            relation = attrs.get('rel')
            if relation == 'EditURI':
                self.set_api_url(attrs['href'].split('?', 1)[0][:-8])
            elif relation == 'stylesheet' and 'href' in attrs:
                try:
                    pos = attrs.get('href').index('/load.php')
                except ValueError:
                    pass
                else:
                    self.set_api_url(attrs['href'][:pos])
                    self.set_version('1.17.0')
            elif relation == 'search' and 'href' in attrs:
                url = attrs['href']
                if url.endswith('opensearch_desc.php'):
                    self.set_api_url(url[:-20])
        elif tag == 'script' and 'src' in attrs:
            try:
                pos = attrs['src'].index('/load.php')
            except ValueError:
                pass
            else:
                self.set_api_url(attrs['src'][:pos])
                self.set_version('1.17.0')
