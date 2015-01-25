# -*- coding: utf-8  -*-
"""Test Interwiki Graph functionality."""
#
# (C) Pywikibot team, 2015
#
# Distributed under the terms of the MIT license.
#
__version__ = '$Id$'

import pywikibot

from pywikibot import interwiki_graph

from tests.aspects import unittest, TestCase


class TestWiktionaryGraph(TestCase):

    """Tests for interwiki links to local sites."""

    sites = {
        'en': {
            'family': 'wiktionary',
            'code': 'en',
        },
        'fr': {
            'family': 'wiktionary',
            'code': 'fr',
        },
        'pl': {
            'family': 'wiktionary',
            'code': 'pl',
        },
    }
    dry = True

    @classmethod
    def setUpClass(cls):
        if not interwiki_graph.pydot:
            raise unittest.SkipTest('pydot not installed')
        super(TestWiktionaryGraph, cls).setUpClass()

    def test_simple_graph(self):
        """Test that GraphDrawer.createGraph does not raise exception."""
        en = pywikibot.Page(self.get_site('en'), 'origin')
        fr = pywikibot.Page(self.get_site('fr'), 'origin')
        pl = pywikibot.Page(self.get_site('pl'), 'origin')

        # Avoid calling server for this test
        en.exists = lambda: True
        fr.exists = lambda: True
        pl.exists = lambda: True

        en.isRedirectPage = en.isDisambig = lambda: False
        fr.isRedirectPage = fr.isDisambig = lambda: False
        pl.isRedirectPage = pl.isDisambig = lambda: False

        # Build data and create graph
        data = interwiki_graph.Subject(en)

        data.foundIn[en] = [fr, pl]
        data.foundIn[fr] = [en, pl]
        data.foundIn[pl] = [en, fr]

        drawer = interwiki_graph.GraphDrawer(data)

        drawer.createGraph()

    def test_octagon(self):
        """Test octagon nodes."""
        en = pywikibot.Page(self.get_site('en'), 'origin')
        en2 = pywikibot.Page(self.get_site('en'), 'origin2')
        fr = pywikibot.Page(self.get_site('fr'), 'origin')
        pl = pywikibot.Page(self.get_site('pl'), 'origin')

        # Avoid calling server for this test
        en.exists = lambda: True
        en2.exists = lambda: True
        fr.exists = lambda: True
        pl.exists = lambda: True

        en.isRedirectPage = en.isDisambig = lambda: False
        en2.isRedirectPage = en2.isDisambig = lambda: False
        fr.isRedirectPage = fr.isDisambig = lambda: False
        pl.isRedirectPage = pl.isDisambig = lambda: False

        # Build data and create graph
        data = interwiki_graph.Subject(en)

        data.foundIn[en] = [fr, pl]
        data.foundIn[en2] = [fr]
        data.foundIn[fr] = [en, pl]
        data.foundIn[pl] = [en, fr]

        drawer = interwiki_graph.GraphDrawer(data)

        drawer.createGraph()

        nodes = drawer.graph.obj_dict['nodes']
        self.assertEqual(
            nodes['""pl:origin""'][0]['attributes']['shape'],
            'rectangle')

        self.assertEqual(
            nodes['""fr:origin""'][0]['attributes']['shape'],
            'rectangle')

        self.assertEqual(
            nodes['""en:origin""'][0]['attributes']['shape'],
            'octagon')


if __name__ == '__main__':
    try:
        unittest.main()
    except SystemExit:
        pass
