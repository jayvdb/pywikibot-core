#!/usr/bin/python
# -*- coding: utf-8  -*-
"""Tests Python features."""
#
# (C) Pywikibot team, 2015
#
# Distributed under the terms of the MIT license.
from __future__ import unicode_literals

__version__ = '$Id$'

import unicodedata

from pywikibot.tools import PYTHON_VERSION

from tests.aspects import TestCase, unittest
from tests.utils import expected_failure_if

# TODO:
# very old
# http://bugs.python.org/issue2517
#
# unicode
# http://sourceforge.net/p/pywikipediabot/bugs/1246/
# http://bugs.python.org/issue10254
#
# ip
# http://bugs.python.org/issue22282
#
# http://bugs.python.org/issue7559
#
# diff
# http://bugs.python.org/issue2142
# http://bugs.python.org/issue11747
# http://sourceforge.net/p/pywikipediabot/bugs/509/
# https://phabricator.wikimedia.org/T57329
# http://bugs.python.org/issue1528074
# http://bugs.python.org/issue1678345


class PythonTestCase(TestCase):

    """Test Python bugs and features."""

    net = False

    @expected_failure_if(PYTHON_VERSION == (2, 6, 6) or
                         (PYTHON_VERSION >= (2, 7) and
                          PYTHON_VERSION < (2, 7, 2)))
    def test_issue_10254(self):
        """Test Python issue #10254."""
        # Python 2.7.1 and below have a bug in this routine.
        # See T102461 and http://bugs.python.org/issue10254
        text = '\u0930\u094d\u0915 \u091c\u093c\u0941'
        #text = '\u0B47\u0300\u0B3E'
        #text = '\u1100\u0300\u1161'
        result = (text == unicodedata.normalize('NFC', text))
        self.assertTrue(result)


if __name__ == "__main__":
    try:
        unittest.main()
    except SystemExit:
        pass
