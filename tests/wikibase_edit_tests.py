# -*- coding: utf-8  -*-
"""Tests for editing Wikibase items."""
#
# (C) Pywikibot team, 2014-2015
#
# Distributed under the terms of the MIT license.
#
from __future__ import unicode_literals

__version__ = '$Id$'
#

import time

import pywikibot

from pywikibot.page import ItemPage

from tests.aspects import unittest, WikibaseTestCase


class TestWikibaseWriteGeneral(WikibaseTestCase):

    """Run general wikibase write tests."""

    family = 'wikidata'
    code = 'test'

    user = True
    write = True

    def test_label_set(self):
        """Test setting an English label."""
        testsite = self.get_repo()
        item = pywikibot.ItemPage(testsite, 'Q68')
        self.assertIsInstance(item, pywikibot.ItemPage)
        self.assertEqual(item.getID(), 'Q68')
        item.editLabels({'en': 'Test123'})
        item.get(force=True)
        self.assertEqual(item.labels['en'], 'Test123')

    def test_label_remove(self):
        """Test adding a Farsi and English label and removing the Farsi one."""
        testsite = self.get_repo()
        item = pywikibot.ItemPage(testsite, 'Q68')
        # These two should be additive
        item.editLabels({'en': 'Test123'})
        item.editLabels({'fa': 'Test123'})
        item.get(force=True)
        self.assertIn('en', item.labels.keys())
        self.assertIn('fa', item.labels.keys())

        # This should remove the 'fa' label
        item.editLabels({'en': 'Test123', 'fa': ''})

        # Check 'fa' label is removed
        item = pywikibot.ItemPage(testsite, 'Q68')
        item.get()
        self.assertNotIn('fa', item.labels.keys())

    def test_alias_set(self):
        """Test setting an English alias."""
        testsite = self.get_repo()
        ts = str(time.time())
        item = pywikibot.ItemPage(testsite, 'Q68')
        item.editAliases({'en': [ts]})

    def test_add_claim_with_qualifier(self):
        """Test adding a claim with a qualifier to an item and a property."""
        testsite = self.get_repo()
        item = pywikibot.ItemPage(testsite, 'Q68')
        item.get()
        if 'P115' in item.claims:
            item.removeClaims(item.claims['P115'])

        claim = pywikibot.page.Claim(testsite, 'P115', datatype='wikibase-item')
        target = pywikibot.ItemPage(testsite, 'Q271')
        claim.setTarget(target)

        item.addClaim(claim)

        item.get(force=True)

        end_date = pywikibot.page.Claim(testsite, 'P88', isQualifier=True)
        end_date.setTarget(pywikibot.WbTime(year=2012))
        item.claims['P115'][0].addQualifier(end_date)

        # Testing all again but this time in properties
        item = pywikibot.PropertyPage(testsite, 'P115')
        item.get()
        if 'P115' in item.claims:
            to_remove = []
            for claim in item.claims['P115']:
                to_remove.append({'id': claim.toJSON()['id'], 'remove': ''})
            item.editEntity({'claims': to_remove})

        claim = pywikibot.page.Claim(testsite, 'P115', datatype='wikibase-item')
        target = pywikibot.ItemPage(testsite, 'Q271')
        claim.setTarget(target)
        item.editEntity({'claims': [claim.toJSON()]})

        item.get(force=True)

        end_date = pywikibot.page.Claim(testsite, 'P88', isQualifier=True)
        end_date.setTarget(pywikibot.WbTime(year=2012))
        item.claims['P115'][0].addQualifier(end_date)

    def test_edit_entity_new_item(self):
        """Test creating a new item using C{ItemPage.editEntity}."""
        testsite = self.get_repo()
        ts = str(time.time())
        data = {
            'labels': {
                'en': {
                    'language': 'en',
                    'value': 'Pywikibot test new item',
                }
            },
            'descriptions': {
                'en': {
                    'language': 'en',
                    'value': 'Pywikibot test new item - ' + ts,
                }
            }
        }
        item = pywikibot.ItemPage(testsite)
        item.editEntity(data)

    def test_edit_entity_new_linked_item(self):
        """Test linking a page using a new item."""
        ts = str(time.time())

        # Create a new page, which is unlinked
        site = self.get_site()
        title = 'Wikidata:Test ' + ts
        page = pywikibot.Page(site, title)
        page.text = ts
        page.save()

        data = {
            'labels': {
                'en': {
                    'language': 'en',
                    'value': 'Pywikibot test new linked item',
                }
            },
            'sitelinks': {
                page.site.dbName(): {
                    'site': page.site.dbName(),
                    'title': page.title()
                }
            },
        }

        repo = self.get_repo()
        item = pywikibot.ItemPage(repo)
        self.assertEqual(item._defined_by(), dict())
        item.editEntity(data)


class TestWikibaseWriteRedirect(WikibaseTestCase):

    """Run general wikibase write tests."""

    family = 'wikidata'
    code = 'test'

    user = True
    write = True

    def test_set_redirect_target(self):
        """Test set_redirect_target method on existing redirect."""
        testsite = self.get_repo()
        item = pywikibot.ItemPage(testsite, 'Q1107')
        target_id = 'Q68'
        if not item.isRedirectPage():
            item.editEntity(data={}, clear=True)
        elif item.getRedirectTarget().getID() == 'Q68':
            target_id = 'Q67'
        target_item = pywikibot.ItemPage(testsite, target_id)
        item.set_redirect_target(target_id, force=True)
        self.assertTrue(item.isRedirectPage())
        new_item = pywikibot.ItemPage(testsite, item.getID())
        self.assertTrue(new_item.isRedirectPage())
        self.assertEqual(new_item.getRedirectTarget(), target_item)

    def test_create_redirect_immediate(self):
        """Test converting a non-empty item into a redirect."""
        target = ItemPage(self.repo, 'Q1593')

        redirect = ItemPage(self.repo)
        redirect.editEntity({})

        redirect.set_redirect_target(target, save=True, force=True)
        self.assertTrue(redirect.isRedirectPage())
        self.assertEqual(redirect.getRedirectTarget(), target)

    @unittest.expectedFailure  # T112243
    def test_edit_redirect(self):
        """Test Itempage.editEntity with a redirect."""
        redirect = ItemPage(self.repo, 'Q1107')
        self.assertTrue(redirect.isRedirectPage())
        old_id = redirect.id

        # trying to convert a redirect to a normal item fails here.
        redirect.editEntity({}, clear=True)
        self.assertFalse(redirect.isRedirectPage())
        self.assertEqual(redirect.id, old_id)
        redirect.get(force=True)
        self.assertFalse(redirect.isRedirectPage())
        self.assertEqual(redirect.id, old_id)


if __name__ == '__main__':
    try:
        unittest.main()
    except SystemExit:
        pass
