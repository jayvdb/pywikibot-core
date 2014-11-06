# -*- coding: utf-8  -*-
"""Family module for Wikia."""

__version__ = '$Id$'

from pywikibot import family


class Family(family.AutoSubdomainFamily):

    """Family class for the Wikia wikis."""

    name = u'wikia'
    domain = 'wikia.com'

    # Only these codes are considered to be have native support
    # currently in pywikibot, and will load without a warning.

    codes = ['www', 'community', 'lyrics']

    # If you just want the warning to go away, add your Wikia subdomain to
    # the codes variable above.

    # TODO: improve the detection logic and test suite to better
    # understand the Wikia farm naming system, in order that additional
    # sites can be natively supported yet ensuring that this family class
    # can not instantiate an invalid wiki site object without a warning.

    obsolete = {
        'wikia': 'www',
        'en': 'www',
    }

    # This is part of the invalid wiki detection algorithm.  See family.py
    invalid_redirect_target_codes = ['community']

    def scriptpath(self, code):
        """Return the script path for this family."""
        return ''
