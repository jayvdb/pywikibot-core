# -*- coding: utf-8  -*-
"""Collection of fixes for tests."""
from __future__ import unicode_literals

# flake8 cannot detect that fixes is defined via pywikibot.fixes, but also it
# cannot detect that the line below won't be executed
if False:
    fixes = {}

fixes['has-msg'] = {
    'regex': False,
    'msg': {
        'en': 'en',
        'de': 'de',
    },
    'replacements': [
        ('1', '2'),
    ]
}

fixes['has-msg-tw'] = {
    'regex': False,
    'msg': 'replace-replacing',
    'replacements': [
        ('1', '2'),
    ]
}

fixes['no-msg'] = {
    'regex': False,
    'replacements': [
        ('1', '2'),
    ]
}

fixes['has-msg-multiple'] = {
    'regex': False,
    'msg': {
        'en': 'en',
        'de': 'de',
    },
    'replacements': [
        ('1', '2'),
        ('3', '4'),
        ('5', '6'),
    ]
}
