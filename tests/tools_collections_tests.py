#!/usr/bin/python
# -*- coding: utf-8  -*-
"""Test tools.collections package."""
#
# (C) Pywikibot team, 2015
#
# Distributed under the terms of the MIT license.
from __future__ import absolute_import, unicode_literals

__version__ = '$Id$'

from collections import defaultdict

from pywikibot.tools.collections import (
    DefaultKeyDict,
    DefaultValueDict,
    InverseSet,
    LimitedKeysDefaultDict,
    StarListDict,
    StarNestedDict,
)

from tests.aspects import TestCase, unittest


class TestDefaultValueDict(TestCase):

    """Test DefaultValueDict."""

    net = False

    def test_copy(self):
        """Test copy()."""
        container = DefaultValueDict('foo', None, {'a': 'b', 'c': 'd'})
        self.assertEqual(container.default_value, 'foo')
        self.assertEqual(container, {'a': 'b', 'c': 'd'})
        copy = container.copy()
        self.assertEqual(copy.default_value, 'foo')
        self.assertEqual(copy, {'a': 'b', 'c': 'd'})


class TestDefaultKeyDict(TestCase):

    """Test TestDefaultKeyDict."""

    net = False

    def test_repr(self):
        """Test repr."""
        container = DefaultKeyDict('*', None, {'a': 'b', 'c': 'd'})
        self.assertEqual(container.default_key, '*')
        self.assertEqual(container, {'a': 'b', 'c': 'd'})
        self.assertEqual(repr(container),
                         'DefaultKeyDict({0!r}, {1})'.format(
                             '*',
                             {'a': 'b', 'c': 'd'}))

    def test_copy(self):
        """Test copy()."""
        container = DefaultKeyDict('*', None, {'a': 'b', 'c': 'd'})
        self.assertEqual(container.default_key, '*')
        self.assertEqual(container, {'a': 'b', 'c': 'd'})
        copy = container.copy()
        self.assertEqual(copy.default_key, '*')
        self.assertEqual(copy, {'a': 'b', 'c': 'd'})

    def test_no_default_factory(self):
        """Test default_factory is not accessible."""
        container = DefaultKeyDict('*')
        with self.assertRaises(AttributeError) as cm:
            getattr(container, 'default_factory')

        self.assertEqual(str(cm.exception), 'default_factory is protected')

    def test_key_star(self):
        """Test key '*'."""
        container = DefaultKeyDict('*')
        self.assertEqual(container.default_key, '*')
        container['*'] = ('en', )
        self.assertEqual(len(container), 0)

        self.assertNotIn('*', container)

        self.assertEqual(container['foo'], ('en', ))
        self.assertEqual(len(container), 1)

        self.assertNotIn('*', container)

        self.assertEqual(container['bar'], ('en', ))
        self.assertEqual(len(container), 2)

        self.assertNotIn('*', container)

        self.assertEqual(container['foo'], ('en', ))

        container['*'] = ('de', )
        self.assertEqual(len(container), 2)
        self.assertEqual(container['foo'], ('en', ))
        self.assertEqual(container['bar'], ('en', ))

        self.assertNotIn('*', container)

        self.assertEqual(container['baz'], ('de', ))
        self.assertEqual(len(container), 3)
        self.assertEqual(container['foo'], ('en', ))
        self.assertEqual(container['bar'], ('en', ))

        self.assertNotIn('*', container)

    def test_key_default(self):
        """Test key '_default'."""
        container = DefaultKeyDict('_default')
        self.assertEqual(container.default_key, '_default')
        container['_default'] = ('en', )
        self.assertEqual(len(container), 0)
        self.assertEqual(container['foo'], ('en', ))
        self.assertEqual(len(container), 1)

        self.assertNotIn('*', container)

    def test_change_default_key(self):
        """Test changing default key."""
        container = DefaultKeyDict('*')
        self.assertEqual(container.default_key, '*')
        self.assertEqual(len(container), 0)
        container['*'] = ('de', )
        self.assertEqual(container['foo'], ('de', ))
        self.assertEqual(len(container), 1)

        container.default_key = '_default'
        container['_default'] = ('en', )
        self.assertEqual(container['bar'], ('en', ))
        self.assertEqual(container['foo'], ('de', ))
        self.assertEqual(len(container), 2)

        self.assertNotIn('*', container)

    def test_initial_dict(self):
        """Test with initial dict."""
        container = DefaultKeyDict('*', None, {'a': 'b', 'c': 'd'})
        self.assertEqual(container.default_key, '*')
        self.assertEqual(container, {'a': 'b', 'c': 'd'})

        container['*'] = ('en', )

        self.assertEqual(container['foo'], ('en', ))
        self.assertEqual(len(container), 3)

        self.assertNotIn('*', container)

    def test_initial_mapping(self):
        """Test with initial dict."""
        mapping = ((key, value) for key, value in {'a': 'b', 'c': 'd'}.items())
        container = DefaultKeyDict('*', None, mapping)
        self.assertEqual(container.default_key, '*')
        self.assertEqual(container, {'a': 'b', 'c': 'd'})

        container['*'] = ('en', )

        self.assertEqual(container['foo'], ('en', ))
        self.assertEqual(len(container), 3)

        self.assertNotIn('*', container)

    def test_initial_keywords(self):
        """Test with initial keyword."""
        container = DefaultKeyDict('*', None, a='b', c='d')
        self.assertEqual(container.default_key, '*')
        self.assertEqual(container, {'a': 'b', 'c': 'd'})

        container['*'] = ('en', )

        self.assertEqual(container['foo'], ('en', ))
        self.assertEqual(len(container), 3)

        self.assertNotIn('*', container)

    def test_initial_dict_with_default(self):
        """Test with default value in initial dict."""
        container = DefaultKeyDict('*', None, {'*': 'b', 'c': 'd'})
        self.assertEqual(container.default_key, '*')
        self.assertEqual(container, {'c': 'd'})
        container['a']
        self.assertEqual(container, {'a': 'b', 'c': 'd'})
        self.assertEqual(len(container), 2)

        self.assertNotIn('*', container)

    def test_initial_keywords_with_default(self):
        """Test with default value in initial keywords."""
        container = DefaultKeyDict('_default', _default='b', c='d')
        self.assertEqual(container.default_key, '_default')
        self.assertEqual(container, {'c': 'd'})
        container['a']
        self.assertEqual(container, {'a': 'b', 'c': 'd'})
        self.assertEqual(len(container), 2)

        self.assertNotIn('*', container)

    def test_update_dict_with_default(self):
        """Test with default value in update(dict)."""
        container = DefaultKeyDict('*')
        container.update({'*': 'b', 'c': 'd'})
        self.assertEqual(container.default_key, '*')
        self.assertEqual(container, {'c': 'd'})
        container['a']
        self.assertEqual(container, {'a': 'b', 'c': 'd'})
        self.assertEqual(len(container), 2)

        self.assertNotIn('*', container)


class TestLimitedKeysDefaultDict(TestCase):

    """Test LimitedKeysDefaultDict."""

    net = False

    def test_normal(self):
        """Test normal defaultdict behaviour."""
        container = LimitedKeysDefaultDict(tuple)
        self.assertEqual(container.default_factory, tuple)
        container._valid_keys = ('foo', 'bar')
        self.assertEqual(len(container), 2)
        self.assertEqual(container.keys(), ('foo', 'bar'))
        self.assertIn('foo', container)
        self.assertIsInstance(container['foo'], tuple)
        self.assertIn('bar', container)
        self.assertNotIn('baz', container)

    def test_initial_values(self):
        """Test instantiation with initial values."""
        container = LimitedKeysDefaultDict(None, {'a': 'b'})
        self.assertEqual(container, {'a': 'b'})

        container = LimitedKeysDefaultDict(None, a='b')
        self.assertEqual(container, {'a': 'b'})

    def test_prevent_invalid(self):
        """Test adding an invalid key."""
        container = LimitedKeysDefaultDict(default_factory=tuple)
        container._valid_keys = ('foo', 'bar')
        self.assertRaises(KeyError, container.__setitem__, 'baz', None)

    def test_set_before_valid(self):
        """Test setting valid keys before list of valid keys is known."""
        container = LimitedKeysDefaultDict(tuple)

        self.assertEqual(container._valid_keys, None)

        self.assertRaises(TypeError, container.__contains__, 'foo')
        self.assertRaises(TypeError, container.items)

        container['foo'] = None
        self.assertRaises(TypeError, container.__contains__, 'foo')
        self.assertRaises(TypeError, container.items)

        container.valid_keys = ('foo', )

        self.assertCountEqual(container._valid_keys, ('foo', ))

        self.assertIn('foo', container)

        self.assertEqual(container['foo'], None)

    def test_cannot_validate(self):
        """Test invalid keys rejected when valid keys is known."""
        container = LimitedKeysDefaultDict(tuple)

        self.assertEqual(container._valid_keys, None)

        self.assertRaises(TypeError, container.__contains__, 'foo')
        self.assertRaises(TypeError, container.items)

        container['foo'] = None
        self.assertRaises(TypeError, container.__contains__, 'foo')
        self.assertRaises(TypeError, container.items)

        self.assertRaises(
            ValueError, container.__setattr__, 'valid_keys', ('bar', ))


class TesteInverseSet(TestCase):

    """Test InverseSet."""

    net = False

    def test_default(self):
        """Test default state which allows any."""
        container = InverseSet()
        self.assertIn('en', container)
        self.assertIn('de', container)

    def test_remove(self):
        """Test default state which allows any."""
        container = InverseSet()
        container.remove('de')
        self.assertIn('en', container)
        self.assertNotIn('de', container)

    def test_with_defaultdict(self):
        """Test as part of a defaultdict."""
        container = defaultdict(InverseSet)
        self.assertIn('en', container['foo'])
        self.assertIn('de', container['foo'])

    def test_with_LimitedKeysDefaultDict(self):
        """Test as part of a LimitedKeysDefaultDict."""
        container = LimitedKeysDefaultDict(InverseSet)
        container._valid_keys = ('foo', 'bar')
        self.assertIn('en', container['foo'])
        self.assertIn('de', container['foo'])
        self.assertIn('en', container['bar'])
        self.assertIn('de', container['bar'])

        container['foo'] = ('en', )
        self.assertIn('en', container['foo'])
        self.assertNotIn('de', container['foo'])
        self.assertIn('en', container['bar'])
        self.assertIn('de', container['bar'])


class TestStarListDict(TestCase):

    """Test StarListDict."""

    net = False

    valid_keys = ('wikipedia', 'wikisource')

    def test_enable_all(self):
        """Test enabling all sites."""
        container = StarListDict()
        container.valid_keys = self.valid_keys

        expect = {
            'wikipedia': ['en', 'de'],
            'wikisource': ['en', 'de'],
        }

        self.assertCountEqual(container, expect)

        self.assertNotIn('wiktionary', container)

        self.assertTrue(container['wikipedia'])
        self.assertTrue(container['wikisource'])
        self.assertRaises(KeyError, container.__getitem__, 'wiktionary')
        self.assertIsNot(container['wikipedia'], container['wikisource'])

        self.assertNotIn('*', container)

    def test_disable_one_site(self):
        """Test disabling only one site."""
        container = StarListDict()
        container.valid_keys = self.valid_keys

        container['wikipedia'].remove('en')

        expect = {
            'wikipedia': ['de'],
            'wikisource': ['en', 'de'],
        }

        self.assertCountEqual(container, expect)

        self.assertTrue(container['wikipedia'])
        self.assertTrue(container['wikisource'])
        self.assertRaises(KeyError, container.__getitem__, 'wiktionary')
        self.assertIsNot(container['wikipedia'], container['wikisource'])

        self.assertNotIn('*', container)

    def test_code_only(self):
        """Test enabling one code on all families."""
        container = StarListDict()
        container.valid_keys = self.valid_keys

        container['*'] = ['en']

        expect = {
            'wikipedia': ['en'],
            'wikisource': ['en'],
        }

        self.assertCountEqual(container, expect)

        self.assertNotIn('wiktionary', container)
        self.assertIsNot(container['wikipedia'], container['wikisource'])

        self.assertNotIn('de', container['wikipedia'])
        self.assertNotIn('de', container['wikisource'])

        self.assertNotIn('*', container)

    def test_multiple_codes(self):
        """Test enabling one code on all families."""
        container = StarListDict()
        container.valid_keys = self.valid_keys

        container['*'] = ['en', 'de']

        expect = {
            'wikipedia': ['en', 'de'],
            'wikisource': ['en', 'de'],
        }

        self.assertCountEqual(container, expect)

        self.assertNotIn('wiktionary', container)
        self.assertIsNot(container['wikipedia'], container['wikisource'])

        self.assertNotIn('ru', container['wikipedia'])
        self.assertNotIn('ru', container['wikisource'])

        self.assertNotIn('*', container)

    def test_code_plus_enable(self):
        """Test enabling one code on all families with additional sites."""
        container = StarListDict()
        container.valid_keys = self.valid_keys

        container['*'] = ['en']
        container['wikipedia'].append('de')
        container['wikisource'].append('ru')

        expect = {
            'wikipedia': ['en', 'de'],
            'wikisource': ['en', 'ru'],
        }

        self.assertCountEqual(container, expect)

        self.assertNotIn('wiktionary', container)
        self.assertIsNot(container['wikipedia'], container['wikisource'])

        self.assertNotIn('ru', container['wikipedia'])
        self.assertNotIn('de', container['wikisource'])

        self.assertNotIn('*', container)

    def test_code_plus_enable_with_disable(self):
        """Test enabling using code with both enable and disable data."""
        container = StarListDict()
        container.valid_keys = self.valid_keys

        container['*'] = ['en']
        container['wikipedia'] = ['ru']
        container['wikisource'].remove('en')

        expect = {
            'wikipedia': ['de'],
            'wikisource': [],
        }

        self.assertCountEqual(container, expect)

        self.assertNotIn('wiktionary', container)
        self.assertIsNot(container['wikipedia'], container['wikisource'])

        self.assertNotIn('en', container['wikipedia'])
        self.assertNotIn('de', container['wikipedia'])
        self.assertNotIn('en', container['wikisource'])
        self.assertNotIn('de', container['wikisource'])
        self.assertNotIn('ru', container['wikisource'])

        self.assertNotIn('*', container)

    def test_invalid_key(self):
        """Test applying limit after configuring."""
        container = StarListDict()
        container.valid_keys = self.valid_keys

        self.assertRaises(KeyError, container.__setitem__, 'wiktionary', 'ru')

    def test_delayed_limit(self):
        """Test applying limit after configuring."""
        container = StarListDict()

        container['*'] = ['en']
        container['wikipedia'] = ['ru']
        container['wikisource'].append('de')
        container['wikisource'].remove('en')

        container.valid_keys = self.valid_keys

        expect = {
            'wikipedia': ['en', 'ru'],
            'wikisource': ['de'],
        }

        self.assertCountEqual(container, expect)


class TestStarNestedDict(TestCase):

    """Test StarNestedDict."""

    net = False

    families = ('wikipedia', 'wikisource')

#    def test_invalid_setitem(self):
#        """Test setting a language key to an invalid value."""
#        container = StarNestedDict()
#
#        container['wikipedia'] = None  # this should be an error??
#
#        self.assertIn('wikipedia', container)
#
#        self.assertNotIn('*', container)
#        self.assertNotIn('*', container['wikipedia'])

    def test_copy(self):
        """Test copy()."""
        container = StarNestedDict(levels=2)

        container['wikipedia']['en'] = 'MyUsername'

        copy = container.copy()
        self.assertCountEqual(container, copy)

    def test_single_site(self):
        """Test enabling all sites."""
        container = StarNestedDict(levels=2)

        container['wikipedia']['en'] = 'MyUsername'

        self.assertNotIn('*', container)
        self.assertNotIn('*', container['wikipedia'])

        self.assertIn('wikipedia', container)
        self.assertIn('wikisource', container)

        self.assertNotIn('*', container)
        self.assertNotIn('*', container['wikipedia'])

        self.assertTrue(container['wikipedia'])
        self.assertFalse(container['wikisource'])
        self.assertIsNot(container['wikipedia'], container['wikisource'])

        self.assertIn('en', container['wikipedia'])
        self.assertNotIn('de', container['wikipedia'])
        self.assertNotIn('*', container['wikipedia'])
        self.assertNotIn('en', container['wikisource'])
        self.assertNotIn('de', container['wikisource'])
        self.assertNotIn('*', container['wikisource'])

        self.assertEqual(container['wikipedia']['en'], 'MyUsername')
        self.assertRaises(KeyError, container['wikipedia'].__getitem__, 'de')
        self.assertRaises(KeyError, container['wikisource'].__getitem__, 'en')

    def test_single_family(self):
        """Test enabling all sites."""
        container = StarNestedDict(levels=2)

        container['wikipedia']['*'] = 'MyUsername'

        self.assertIn('wikipedia', container)
        self.assertIn('wikisource', container)

        self.assertNotIn('*', container)
        self.assertNotIn('*', container['wikipedia'])

        self.assertTrue(container['wikipedia'])
        self.assertFalse(container['wikisource'])
        self.assertIsNot(container['wikipedia'], container['wikisource'])

        self.assertIn('en', container['wikipedia'])
        self.assertIn('de', container['wikipedia'])
        self.assertNotIn('*', container['wikipedia'])
        self.assertNotIn('en', container['wikisource'])
        self.assertNotIn('de', container['wikisource'])
        self.assertNotIn('*', container['wikisource'])

        self.assertEqual(container['wikipedia']['en'], 'MyUsername')
        self.assertEqual(container['wikipedia']['de'], 'MyUsername')
        self.assertRaises(KeyError, container['wikisource'].__getitem__, 'en')

    def test_multiple_usernames(self):
        """Test enabling all sites."""
        container = StarNestedDict(levels=2)

        container['wikipedia']['de'] = 'MyUsernameDe'
        container['wikipedia']['en'] = 'MyUsernameEn'

        self.assertIn('wikipedia', container)
        self.assertIn('wikisource', container)

        self.assertNotIn('*', container)
        self.assertNotIn('*', container['wikipedia'])

        self.assertTrue(container['wikipedia'])
        self.assertFalse(container['wikisource'])
        self.assertIsNot(container['wikipedia'], container['wikisource'])

        self.assertIn('en', container['wikipedia'])
        self.assertIn('de', container['wikipedia'])
        self.assertNotIn('*', container['wikipedia'])
        self.assertNotIn('ru', container['wikipedia'])
        self.assertNotIn('en', container['wikisource'])
        self.assertNotIn('de', container['wikisource'])
        self.assertNotIn('*', container['wikisource'])

        self.assertEqual(container['wikipedia']['en'], 'MyUsernameEn')
        self.assertEqual(container['wikipedia']['de'], 'MyUsernameDe')
        self.assertRaises(KeyError, container['wikisource'].__getitem__, 'ru')
        self.assertRaises(KeyError, container['wikisource'].__getitem__, 'en')

    def test_username_override(self):
        """Test enabling all sites."""
        container = StarNestedDict(levels=2)

        container['wikipedia']['*'] = 'MyUsername'
        container['wikipedia']['en'] = 'MyUsernameEn'

        self.assertIn('wikipedia', container)
        self.assertIn('wikisource', container)

        self.assertNotIn('*', container)
        self.assertNotIn('*', container['wikipedia'])

        self.assertTrue(container['wikipedia'])
        self.assertFalse(container['wikisource'])
        self.assertIsNot(container['wikipedia'], container['wikisource'])

        self.assertIn('en', container['wikipedia'])
        self.assertIn('de', container['wikipedia'])
        self.assertIn('ru', container['wikipedia'])
        self.assertNotIn('*', container['wikipedia'])
        self.assertNotIn('en', container['wikisource'])
        self.assertNotIn('de', container['wikisource'])
        self.assertNotIn('*', container['wikisource'])

        self.assertEqual(container['wikipedia']['en'], 'MyUsernameEn')
        self.assertEqual(container['wikipedia']['de'], 'MyUsername')
        self.assertEqual(container['wikipedia']['ru'], 'MyUsername')
        self.assertRaises(KeyError, container['wikisource'].__getitem__, 'ru')
        self.assertRaises(KeyError, container['wikisource'].__getitem__, 'en')

if __name__ == '__main__':
    try:
        unittest.main()
    except SystemExit:
        pass
