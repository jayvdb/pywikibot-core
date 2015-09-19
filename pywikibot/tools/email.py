# -*- coding: utf-8  -*-
"""Workaround for Python issue 19003. See T113120."""
#
# (C) Pywikibot team, 2014
#
# Distributed under the terms of the MIT license.
#
from __future__ import absolute_import, unicode_literals

__version__ = '$Id$'


from io import BytesIO

import email.generator
from email.mime.multipart import MIMEMultipart as MIMEMultipartOrig


class CTEBinaryBytesGenerator(email.generator.BytesGenerator):

    """Workaround for bug in python 3 email handling of CTE binary."""

    def __init__(self, *args, **kwargs):
        """Constructor."""
        super(CTEBinaryBytesGenerator, self).__init__(*args, **kwargs)
        self._writeBody = self._write_body

    def _write_body(self, msg):
        if msg['content-transfer-encoding'] == 'binary':
            self._fp.write(msg.get_payload(decode=True))
        else:
            super(CTEBinaryBytesGenerator, self)._handle_text(msg)


class CTEBinaryMIMEMultipart(MIMEMultipartOrig):

    """Workaround for bug in python 3 email handling of CTE binary."""

    def as_bytes(self, unixfrom=False, policy=None):
        """Return unmodified binary payload."""
        policy = self.policy if policy is None else policy
        fp = BytesIO()
        g = CTEBinaryBytesGenerator(fp, mangle_from_=False, policy=policy)
        g.flatten(self, unixfrom=unixfrom)
        return fp.getvalue()
