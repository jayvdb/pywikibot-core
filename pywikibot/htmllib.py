# -*- coding: utf-8  -*-
"""Functions for manipulating html."""
#
# (C) Pywikibot team, 2015
#
# Distributed under the terms of the MIT license.
#
from __future__ import unicode_literals

__version__ = '$Id$'
#

from collections import defaultdict

from pywikibot.tools import PY2

if not PY2:
    from html.parser import HTMLParser
else:
    from HTMLParser import HTMLParser


class WikiSiteHTMLMainPageParser(HTMLParser):

    """Wiki HTML page parser."""

    def __init__(self, *args, **kwargs):
        HTMLParser.__init__(self, *args, **kwargs)
        self.generator = None

    def handle_starttag(self, tag, attrs):
        attrs = defaultdict(lambda: None, attrs)
        if tag == "meta":
            if attrs["name"] == "generator":
                self.generator = attrs["content"]
        if tag == "link":
            if attrs["rel"] == "EditURI":
                self.edituri = attrs["href"]



