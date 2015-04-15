#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Script that forms part of pwb_tests."""
from __future__ import unicode_literals

import os
import sys

_pwb_dir = os.path.abspath(os.path.join(os.path.split(__file__)[0], '..', '..'))

print('os.environ:')
for k, v in sorted(os.environ.items()):
    if k in ['PYWIKIBOT2_DIR_PWB']:
        continue
    print("%r: %r" % (k, v))

print('sys.path:', _pwb_dir)
for path in sys.path:
    if path == '' or path.startswith('.') or path.startswith(_pwb_dir):
        continue
    print(path)

