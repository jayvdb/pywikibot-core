# -*- coding: utf-8  -*-
"""
Basic HTTP access interface.

This module handles communication between the bot and the HTTP threads.

This module is responsible for
    - Setting up a connection pool
    - Providing a (blocking) interface for HTTP requests
    - Translate site objects with query strings into URLs
    - URL-encoding all data
    - Basic HTTP error handling
"""

#
# (C) Pywikibot team, 2007-2014
#
# Distributed under the terms of the MIT license.
#

__version__ = '$Id$'
__docformat__ = 'epytext'

import sys
import atexit
import time
import cookielib
import pywikibot
from pywikibot import config
from pywikibot.tools import deprecate_arg
import requests

_logger = 'lolhttp'

cookie_jar = cookielib.LWPCookieJar(
    config.datafilepath("pywikibot.lwp2")
)
try:
    cookie_jar.load()
except (IOError, cookielib.LoadError):
    pywikibot.debug(u"Loading cookies failed.", _logger)
else:
    pywikibot.debug(u"Loaded cookies from file.", _logger)

# export cookie_jar to global namespace
pywikibot.cookie_jar = cookie_jar

session = requests.Session()
session.cookies=cookie_jar

USER_AGENT_PRODUCTS = {
    'python': 'Python/' + '.'.join([str(i) for i in sys.version_info]),
    'backend': 'requests/' + requests.__version__,
    'pwb': 'Pywikibot/' + pywikibot.__release__,
}


def user_agent_username(username=None):
    """
    Reduce username to a representation permitted in HTTP headers.

    To achieve that, this function:
    1) replaces spaces (' ') with '_'
    2) encodes the username as 'utf-8' and if the username is not ASCII
    3) URL encodes the username if it is not ASCII, or contains '%'
    """
    if not username:
        return ''
    username = username.replace(' ', '_')  # Avoid spaces or %20.
    try:
        username.encode('ascii')  # just test, but not actually use it
    except UnicodeEncodeError:
        pass
    else:
        # % is legal in the default $wgLegalTitleChars
        # This is so that ops know the real pywikibot will not
        # allow a useragent in the username to allow through a hand-coded
        # percent-encoded value.
        if '%' in username:
            return quote(username)
        else:
            return username
    username = quote(username.encode('utf-8'))
    return username


def user_agent(site=None, format_string=None):
    """
    Generate the user agent string for a given site and format.

    @param site: The site for which this user agent is intended. May be None.
    @type site: BaseSite
    @param format_string: The string to which the values will be added using
        str.format. Is using config.user_agent_format when it is None.
    @type format_string: basestring
    @return: The formatted user agent
    @rtype: unicode
    """
    values = USER_AGENT_PRODUCTS.copy()

    # This is the Pywikibot revision; also map it to {version} at present.
    if pywikibot.version.cache:
        values['revision'] = pywikibot.version.cache['rev']
    else:
        values['revision'] = ''
    values['version'] = values['revision']

    values['script'] = pywikibot.calledModuleName()

    # TODO: script_product should add the script version, if known
    values['script_product'] = pywikibot.calledModuleName()

    script_comments = []
    username = ''
    if site:
        script_comments.append(str(site))

        # TODO: there are several ways of identifying a user, and username
        # is not the best for a HTTP header if the username isnt ASCII.
        if site.username():
            username = user_agent_username(site.username())
            script_comments.append(
                'User:' + username)

    values.update({
        'family': site.family.name if site else '',
        'code': site.code if site else '',
        'lang': site.code if site else '',  # TODO: use site.lang, if known
        'site': str(site) if site else '',
        'username': username,
        'script_comments': '; '.join(script_comments)
    })

    if not format_string:
        format_string = config.user_agent_format

    formatted = format_string.format(**values)
    # clean up after any blank components
    formatted = formatted.replace(u'()', u'').replace(u'  ', u' ').strip()
    return formatted


@deprecate_arg('ssl', None)
def request(site=None, uri=None, charset=None, *args, **kwargs):
    """
    Request to Site with default error handling and response decoding.

    See L{httplib2.Http.request} for additional parameters.

    If the site argument is provided, the uri is a relative uri from
    and including the document root '/'.

    If the site argument is None, the uri must be absolute.

    @param site: The Site to connect to
    @type site: L{pywikibot.site.BaseSite}
    @param uri: the URI to retrieve
    @type uri: str
    @param charset: Either a valid charset (usable for str.decode()) or None
        to automatically chose the charset from the returned header (defaults
        to latin-1)
    @type charset: CodecInfo, str, None
    @return: The received data
    @rtype: a unicode string
    """
    assert(site or uri)
    if not site:
        # TODO: deprecate this usage, once the library code has been
        # migrated to using the other request methods.
        r = fetch(uri, *args, **kwargs)
        return r.content

    baseuri = site.base_url(uri)

    kwargs.setdefault("disable_ssl_certificate_validation",
                      site.ignore_certificate_error())

    format_string = kwargs.setdefault("headers", {}).get("user-agent")
    kwargs["headers"]["user-agent"] = user_agent(site, format_string)
    kwargs['charset'] = charset

    r = fetch(baseuri, *args, **kwargs)
    pywikibot.debug(r.text, _logger)
    return r.text

def fetch(uri, method="GET", body=None, headers=None,
          default_error_handling=True, **kwargs):
    """
    Blocking HTTP request.

    Note: The callback runs in the HTTP thread, where exceptions are logged
    but are not able to be caught.

    See L{httplib2.Http.request} for parameters.

    @param default_error_handling: Use default error handling
    @type default_error_handling: bool
    @rtype: L{threadedhttp.HttpRequest}
    """
    pywikibot.debug("%r %r %r" % (method, uri, body), _logger)
    pywikibot.debug(repr(cookie_jar), _logger)
    import time
    time.sleep(1)
    request = session.request(method, uri, data=body, headers=headers, cookies=cookie_jar)
    return request
