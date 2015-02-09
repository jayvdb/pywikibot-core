# -*- coding: utf-8  -*-
"""Variable like database using SQlite3."""
#
# (C) Mjbmr, 2015
# (C) Pywikibot team, 2015
#
# Distributed under the terms of the MIT license.
#

__version__ = '$Id$'

import sqlite3

try:
    import cPickle as pickle
except:
    import pickle


class DataSet:

    """Variable like database using SQlite3."""

    def __init__(self, filename=None, top=None, top_id=0):
        self.top_id = top_id
        self.top = top
        if top is not None:
            self.db = top.db
            self.cur = self.db.cursor()
        else:
            self.db = sqlite3.connect(filename, check_same_thread=False)
            self.cur = self.db.cursor()
            self.cur.execute('PRAGMA foreign_keys = ON')
            self.cur.execute(
                'CREATE TABLE IF NOT EXISTS `data` '
                '(`id` INTEGER PRIMARY KEY AUTOINCREMENT, `key` TEXT,'
                ' `value` TEXT,`top` INTEGER, `item_count`'
                ' INTEGER DEFAULT 0, UNIQUE(`key`, `value`, `top`,'
                ' `item_count`), FOREIGN KEY (`top`) REFERENCES'
                ' `data`(`id`) ON DELETE CASCADE)'
            )
            try:
                self.cur.execute('INSERT INTO `data` (`id`) VALUES (0)')
            except sqlite3.IntegrityError:
                pass
            self.db.commit()
        self._length = 0
        self._value = None
        self.cur.execute('SELECT * FROM `data` WHERE `id` = ?', (self.top_id,))
        for row in self.cur:
            if not row[2] is None:
                self._value = pickle.loads(row[2].encode('utf-8'))
            self._length = row[4]
        if self.top_id == 0:
            self._value = {}
        if type(self._value) == list:
            self.append = self._append

    def _append(self, value):
        return self.__setitem__(self._length, value)

    def __setitem__(self, key, value, no_commit=False):
        if not no_commit:
            self.cur.execute("vacuum")
            self.db.commit()
        packed_key = pickle.dumps(key)
        self.cur.execute(
            'SELECT * FROM `data` WHERE `key` = ? AND `top` = ?',
            (packed_key, self.top_id)
        )
        found = None
        for row in self.cur:
            found = row
        if found:
            key_id = found[0]
            self.cur.execute('DELETE FROM `data` WHERE `top` = ?', (key_id,))
            if not no_commit:
                self.db.commit()
            if type(value) == dict:
                packed_dict = pickle.dumps({})
                self.cur.execute(
                    'UPDATE `data` SET `value` = ?,'
                    '`item_count` = 0 WHERE `id` = ?',
                    (packed_dict, key_id)
                )
                for subkey in value:
                    subvalue = value[subkey]
                    DataSet(top=self, top_id=key_id).__setitem__(
                        subkey, subvalue, no_commit=True)
                self.db.commit()
            elif type(value) == list:
                packed_list = pickle.dumps([])
                self.cur.execute(
                    'UPDATE `data` SET `value` = ?, `item_count` = 0'
                    ' WHERE `id` = ?',
                    (packed_list, key_id)
                )
                for subkey in range(0, len(value)):
                    subvalue = value[subkey]
                    DataSet(top=self, top_id=key_id).__setitem__(
                        subkey, subvalue, no_commit=True)
                self.db.commit()
            else:
                packed_value = pickle.dumps(value)
                self.cur.execute('UPDATE `data` SET `value` = ? WHERE id = ?',
                                 (packed_value, found[0]))
                if not no_commit:
                    self.db.commit()
        else:
            if type(value) == dict:
                packed_dict = pickle.dumps({})
                self.cur.execute(
                    'INSERT INTO `data` (`key`, `value`, `top`)'
                    'VALUES (?, ?, ?)',
                    (packed_key, packed_dict, self.top_id)
                )
                key_id = self.cur.lastrowid
                self.db.commit()
                for subkey in value:
                    subvalue = value[subkey]
                    DataSet(top=self, top_id=key_id).__setitem__(
                        subkey, subvalue, no_commit=True)
                self.db.commit()
            elif type(value) == list:
                packed_list = pickle.dumps([])
                self.cur.execute(
                    'INSERT INTO `data` (`key`, `value`, `top`)'
                    'VALUES (?, ?, ?)',
                    (packed_key, packed_list, self.top_id)
                )
                key_id = self.cur.lastrowid
                self.db.commit()
                for subkey in range(0, len(value)):
                    subvalue = value[subkey]
                    DataSet(top=self, top_id=key_id).__setitem__(
                        subkey, subvalue, no_commit=True)
                self.db.commit()
            else:
                packed_value = pickle.dumps(value)
                self.cur.execute(
                    'INSERT INTO `data` (`key`, `value`, `top`) '
                    'VALUES (?, ?, ?)',
                    (packed_key, packed_value, self.top_id)
                )
                if not no_commit:
                    self.db.commit()
            if self.top:
                self.top._length += 1
            self.cur.execute(
                'UPDATE `data` SET `item_count` = `item_count` +'
                ' 1 WHERE `id` = ?',
                (self.top_id,)
            )
            self.db.commit()

    def __getitem__(self, key):
        packed_key = pickle.dumps(key)
        self.cur.execute(
            'SELECT * FROM `data` WHERE `key` = ? AND `top` = ?',
            (packed_key, self.top_id)
        )
        found = None
        for row in self.cur:
            found = row
        if found:
            key_id = found[0]
            value = found[2]
            unpacked_value = pickle.loads(value.encode('utf-8'))
            if type(unpacked_value) == dict:
                return DataSet(top=self, top_id=key_id)
            elif type(unpacked_value) == list:
                return DataSet(top=self, top_id=key_id)
            else:
                return unpacked_value
        else:
            raise KeyError('%s' % key)

    def __contains__(self, key):
        packed_key = pickle.dumps(key)
        if type(self._value) == dict:
            self.cur.execute(
                'SELECT * FROM `data` WHERE `key` = ? AND `top` = ? LIMIT 1',
                (packed_key, self.top_id)
            )
        elif type(self._value) == list:
            self.cur.execute(
                'SELECT * FROM `data` WHERE `value` = ? AND `top` = ? LIMIT 1',
                (packed_key, self.top_id)
            )
        else:
            return None
        return bool(list(self.cur))

    def __nonzero__(self):
        return True

    def __len__(self):
        return self._length

    def __delitem__(self, key):
        packed_key = pickle.dumps(key)
        self.cur.execute(
            'DELETE FROM `data` WHERE `key` = ? AND `top` = ?',
            (packed_key, self.top_id)
        )
        self.db.commit()
        return True

    def __str__(self):
        if type(self._value) == dict:
            d = {}
            self.cur.execute(
                'SELECT * FROM `data` WHERE `top` = ? LIMIT %d' % self._length,
                (self.top_id,)
            )
            for row in self.cur:
                key = row[1]
                unpacked_key = pickle.loads(key.encode('utf-8'))
                d[unpacked_key] = DataSet(
                    top=self, top_id=self.top_id)[unpacked_key]
            return str(d)
        elif type(self._value) == list:
            d = []
            self.cur.execute(
                'SELECT * FROM `data` WHERE `top` = ? LIMIT %d' % self._length,
                (self.top_id,)
            )
            for row in self.cur:
                key = row[1]
                unpacked_key = pickle.loads(key.encode('utf-8'))
                d.append(DataSet(top=self, top_id=self.top_id)[unpacked_key])
            return str(d)
        else:
            return str(self._value)

    def __repr__(self):
        return str(self)

    def __iter__(self):
        self.cur.execute(
            'SELECT `key` FROM `data` WHERE `top` = ? LIMIT %d' % self._length,
            (self.top_id,)
        )
        for row in self.cur:
            unpacked_key = pickle.loads(row[0].encode('utf-8'))
            if type(self._value) == dict:
                yield unpacked_key
            elif type(self._value) == list:
                yield DataSet(top=self, top_id=self.top_id)[unpacked_key]
