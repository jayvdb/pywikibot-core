# -*- coding: utf-8  -*-
"""Miscellaneous collections classes."""
#
# (C) Pywikibot team, 2015
#
# Distributed under the terms of the MIT license.
#
from __future__ import absolute_import, unicode_literals
__version__ = '$Id$'

from collections import defaultdict, Container, Iterable
from copy import copy
from functools import partial

from pywikibot.tools import PY2

if not PY2:
    basestring = (str, )


class InfiniteSet(Container):

    """A set that is not finite."""

    pass


class InverseSet(InfiniteSet):

    """Set-like container that is the inverse of a set."""

    def __init__(self, inversed=None):
        """Constructor."""
        super(InverseSet, self).__init__()
        self._inversed = inversed

    def append(self, item):
        """Append an item (noop)."""
        pass

    def add(self, item):
        """Add an item (noop)."""
        if self._inversed is not None:
            self._inversed.discard(item)

    def remove(self, item):
        """Remove an item."""
        if self._inversed is None:
            self._inversed = set((item, ))
        elif item in self._inversed:
            raise KeyError('{0} is not present')
        else:
            self._inversed.add(item)

    def discard(self, item):
        """Remove an item if it is present."""
        if self._inversed is None:
            self._inversed = set((item, ))
        else:
            self._inversed.add(item)

    def __contains__(self, item):
        """Return True for any item except items that have been removed."""
        if self._inversed is None:
            return True
        else:
            return item not in self._inversed

    def __sub__(self, other):
        """Subtract operation."""
        if self._inversed is None:
            self._inversed = other
        else:
            self._inversed += other

    def __invert__(self):
        """Invert the infinite set."""
        return self._inversed or set()


class DefaultValueDict(defaultdict):

    """A defaultdict that accepts data instead of a callable."""

    def __init__(self, default_value=None,
                 default_factory=None, *args, **kwargs):
        """Constructor."""
        super(DefaultValueDict, self).__init__(
            default_factory, *args, **kwargs)

        if default_value:
            self.default_value = default_value

    def copy(self):
        """Create a copy."""
        default_factory = super(DefaultValueDict, self).__getattribute__(
            'default_factory')

        try:
            default_value = self.default_value
        except TypeError:
            default_value = None

        return self.__class__(default_value, default_factory, self)

    def __getattribute__(self, attr):
        """Prevent access to default_factory."""
        if attr == 'default_factory':
            raise AttributeError('default_factory is protected')
        else:
            return super(DefaultValueDict, self).__getattribute__(attr)

    def __setattr__(self, attr, value):
        """Prevent access to default_factory."""
        if attr == 'default_factory':
            raise AttributeError('default_factory is protected')
        else:
            return super(DefaultValueDict, self).__setattr__(attr, value)

    @property
    def default_value(self):
        """
        Get default value.

        @raise TypeError: default value was not set
        """
        if not hasattr(self, '_default_value'):
            raise TypeError('default_value accessed before it was set')

        return self._default_value

    @default_value.setter
    def default_value(self, value):
        """Set default value."""
        self._default_value = value
        super(DefaultValueDict, self).__setattr__('default_factory',
                                                  lambda: copy(value))

    def __bool__(self):
        """Return True if the defaultdict contains '*' or a real value."""
        try:
            self.default_value
        except TypeError:
            pass
        else:
            return True

        return self.__len__() != 0

    __nonzero__ = __bool__


class DefaultKeyDict(DefaultValueDict):

    """A default dict with a key which can be used to set the default value."""

    def __init__(self, default_key, default_factory=None, *args, **kwargs):
        """
        Constructor.

        @param default_key: A key which will be interpreted as a default
        """
        super(DefaultKeyDict, self).__init__(
            None, default_factory, *args, **kwargs)
        self.default_key = default_key

        # defaultdict doesnt use __setitem__ or update()
        # so the default key value needs to be extracted after __init__.
        # use super methods to allow subclasses to alter these methods.
        if args or kwargs:
            keys = dict.keys(self)
            if default_key in keys:
                value = dict.__getitem__(self, default_key)
                self[default_key] = value
                del self[default_key]

    def copy(self):
        """Create a copy."""
        default_factory = super(DefaultValueDict, self).__getattribute__(
            'default_factory')

        try:
            default_value = self.default_value
        except TypeError:
            default_value = None

        rv = self.__class__(self.default_key, default_factory, self)
        if default_value:
            rv.default_value = default_value
        return rv

    def __getattribute__(self, attr):
        """Prevent access to default_factory."""
        if attr == 'default_factory':
            raise AttributeError('default_factory is protected')
        else:
            return super(DefaultKeyDict, self).__getattribute__(attr)

    def __setattr__(self, attr, value):
        """Prevent access to default_factory."""
        if attr == 'default_factory':
            raise AttributeError('default_factory is protected')
        else:
            return super(DefaultKeyDict, self).__setattr__(attr, value)

    def __getitem__(self, item):
        """Set item or default."""
        if item == self.default_key:
            raise KeyError('can not use default_key as a key')
        else:
            return super(DefaultKeyDict, self).__getitem__(item)

    def __setitem__(self, item, value):
        """Set item or default."""
        if item == self.default_key:
            super(DefaultKeyDict, self).__setattr__('default_value', value)
        else:
            super(DefaultKeyDict, self).__setitem__(item, value)

    def update(self, other):
        """Update with other."""
        if self.default_key in other:
            self.__setitem__(self.default_key, other[self.default_key])
            other = other.copy()
            del other[self.default_key]

        super(DefaultKeyDict, self).update(other)

    def __repr__(self):
        """Internal representation."""
        return '{0}({1!r}, {2})'.format(self.__class__.__name__,
                                        self.default_key,
                                        repr(dict(self)))


class LimitedKeysDefaultDict(defaultdict):

    """
    A defaultdict with limited keys available.

    Set valid_keys to be the list of valid keys.

    Values may be put into the dict before the list of
    valid keys is set, but they can not be accessed until
    the list of valid keys is set.

    """

    _valid_keys = None

    @property
    def valid_keys(self):
        """
        Get valid keys.

        @raise TypeError: not set
        """
        if self._valid_keys is None:
            raise TypeError('_valid_keys not set')
        return self._valid_keys

    @valid_keys.setter
    def valid_keys(self, value):
        """
        Set valid keys.

        @raise ValueError: existing keys are not valid.
        """
        if not isinstance(value, Iterable):
            raise TypeError('value must be iterable')

        value = set(value)

        existing_keys = set(super(LimitedKeysDefaultDict, self).keys())

        if not existing_keys.issubset(value):
            raise ValueError('existing keys would become invalid')

        self._valid_keys = value

    def derive_valid_keys(self):
        """Force the present keys to be valid."""
        self.valid_keys = dict.keys(self)

    def __setitem__(self, item, value):
        """Return False if item not a valid key."""
        if self._valid_keys is not None and item not in self._valid_keys:
            raise KeyError('_valid_keys does not contain {0}'.format(item))

        super(LimitedKeysDefaultDict, self).__setitem__(item, value)
        assert (item, value) in super(LimitedKeysDefaultDict, self).items()

    def _check_access_allowed(self):
        """Check that valid_keys has been set, or the item is empty."""
        if self._valid_keys is None:
            raise TypeError('_valid_keys not set', self.__class__.__name__)

        # count = super(LimitedKeysDefaultDict, self).__len__()

# This causes all sorts of problems, esp. with copy(), but also with the syntax
#   foo['blah'].append('en')
# as that is a get then modify
#
#    def __getitem__(self, item):
#        """Return False if item not a valid key."""
#        self._check_access_allowed()
#
#        return super(LimitedKeysDefaultDict, self).__getitem__(item)

    def __contains__(self, item):
        """Return False if item not a valid key."""
        self._check_access_allowed()

        return item in self._valid_keys

    def __len__(self):
        """Return length."""
        self._check_access_allowed()
        return len(self._valid_keys)

    def keys(self):
        """Return all valid keys."""
        self._check_access_allowed()
        return self._valid_keys

    def items(self):
        """Return items."""
        self._check_access_allowed()
        return ((key, self[key])
                for key in self._valid_keys)

    def __iter__(self):
        """Return iterator."""
        self._check_access_allowed()
        for key in self._valid_keys:
            yield key


class AutoContainsDefaultDict(defaultdict):

    """Automatically populate dict on __contains__."""

    def __contains__(self, item):
        """Return True if item can be obtained from the dict."""
        try:
            self.__getitem__(item)
            return True
        except KeyError:
            return False


class StarListDict(AutoContainsDefaultDict,
                   DefaultKeyDict,
                   LimitedKeysDefaultDict):

    """A '*' addressable container of lists."""

    def __init__(self, *args, **kwargs):
        """Constructor."""
        super(StarListDict, self).__init__('*', InverseSet, *args, **kwargs)

    def copy(self):
        """Create a copy."""
        return self.__class__(self)


class StarNestedDict(AutoContainsDefaultDict,
                     DefaultKeyDict):

    """A '*' addressable nestable dict."""

    def __init__(self, levels=1, *args, **kwargs):
        """
        Constructor.

        @param levels: Number of nesting levels
        """
        self._levels = levels
        if levels == 1:
            default_factory = None
        else:
            default_factory = partial(self.__class__, levels=levels - 1)

        super(StarNestedDict, self).__init__('*', default_factory,
                                             *args, **kwargs)

    def copy(self):
        """Create a copy."""
        return self.__class__(self._levels, self)
