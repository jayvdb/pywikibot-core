# -*- coding: utf-8 -*-
"""
Objects representing various types of MediaWiki, including Wikibase, pages.

This module also includes objects:

* Property: a type of semantic data.
* Claim: an instance of a semantic assertion.
* Revision: a single change to a wiki page.
* FileInfo: a structure holding imageinfo of latest rev. of FilePage
* Link: an internal or interwiki link in wikitext.

"""
#
# (C) Pywikibot team, 2008-2017
#
# Distributed under the terms of the MIT license.
#
from __future__ import absolute_import, unicode_literals

__version__ = '$Id$'
#

import datetime
import hashlib
import logging
import os.path
import re
import sys
import weakref

try:
    import unicodedata2 as unicodedata
except ImportError:
    import unicodedata

from collections import defaultdict, namedtuple
from warnings import warn

from pywikibot.tools import PY2

if not PY2:
    unicode = basestring = str
    long = int
    from html import entities as htmlentitydefs
    from urllib.parse import quote_from_bytes, unquote_to_bytes
else:
    if __debug__ and not PY2:
        unichr = NotImplemented  # pyflakes workaround

    chr = unichr

    import htmlentitydefs
    from urllib import quote as quote_from_bytes, unquote as unquote_to_bytes

import pywikibot

from pywikibot import config
from pywikibot import textlib

from pywikibot.comms import http
from pywikibot.exceptions import (
    AutoblockUser,
    NotEmailableError,
    SiteDefinitionError,
    UserRightsError,
)
from pywikibot.data.api import APIError
from pywikibot.family import Family
from pywikibot.site import DataSite, Namespace, need_version
from pywikibot.tools import (
    compute_file_hash,
    PYTHON_VERSION,
    MediaWikiVersion, UnicodeMixin, ComparableMixin, DotReadableDict,
    deprecated, deprecate_arg, deprecated_args, issue_deprecation_warning,
    add_full_name, manage_wrapping,
    ModuleDeprecationWrapper as _ModuleDeprecationWrapper,
    first_upper, redirect_func, remove_last_args, _NotImplementedWarning,
    MediaWikiVersion,
    OrderedDict, Counter,
)
from pywikibot.tools.ip import ip_regexp
from pywikibot.tools.ip import is_IP

__all__ = (
    'BasePage',
    'Page',
    'FilePage',
    'Category',
    'User',
    'WikibasePage',
    'ItemPage',
    'Property',
    'PropertyPage',
    'Claim',
    'Revision',
    'FileInfo',
    'Link',
    'html2unicode',
    'UnicodeToAsciiHtml',
    'unicode2html',
    'url2unicode',
    'ip_regexp',  # unused & deprecated
)

logger = logging.getLogger("pywiki.wiki.page")


@add_full_name
def allow_asynchronous(func):
    """
    Decorator to make it possible to run a BasePage method asynchronously.

    This is done when the method is called with kwarg asynchronous=True.
    Optionally, you can also provide kwarg callback, which, if provided, is
    a callable that gets the page as the first and a possible exception that
    occurred during saving in the second thread or None as the second argument.
    """
    def handle(func, self, *args, **kwargs):
        do_async = kwargs.pop('asynchronous', False)
        callback = kwargs.pop('callback', None)
        err = None
        try:
            func(self, *args, **kwargs)
        # TODO: other "expected" error types to catch?
        except pywikibot.Error as edit_err:
            err = edit_err  # edit_err will be deleted in the end of the scope
            link = self.title(asLink=True)
            pywikibot.log('Error saving page %s (%s)\n' % (link, err),
                          exc_info=True)
            if not callback and not do_async:
                if isinstance(err, pywikibot.PageSaveRelatedError):
                    raise err
                raise pywikibot.OtherPageSaveError(self, err)
        if callback:
            callback(self, err)

    def wrapper(self, *args, **kwargs):
        if kwargs.get('asynchronous'):
            pywikibot.async_request(handle, func, self, *args, **kwargs)
        else:
            handle(func, self, *args, **kwargs)

    manage_wrapping(wrapper, func)

    return wrapper


# Note: Link objects (defined later on) represent a wiki-page's title, while
# Page objects (defined here) represent the page itself, including its contents.

class BasePage(UnicodeMixin, ComparableMixin):

    """
    BasePage: Base object for a MediaWiki page.

    This object only implements internally methods that do not require
    reading from or writing to the wiki. All other methods are delegated
    to the Site object.

    Will be subclassed by Page, WikibasePage, and FlowPage.
    """

    _cache_attrs = (
        '_text', '_pageid', '_catinfo', '_templates', '_protection',
        '_contentmodel', '_langlinks', '_isredir', '_coords',
        '_preloadedtext', '_timestamp', '_applicable_protections',
        '_flowinfo', '_quality', '_pageprops', '_revid', '_quality_text'
    )

    def __init__(self, source, title=u"", ns=0):
        """
        Instantiate a Page object.

        Three calling formats are supported:

          - If the first argument is a Page, create a copy of that object.
            This can be used to convert an existing Page into a subclass
            object, such as Category or FilePage. (If the title is also
            given as the second argument, creates a copy with that title;
            this is used when pages are moved.)
          - If the first argument is a Site, create a Page on that Site
            using the second argument as the title (may include a section),
            and the third as the namespace number. The namespace number is
            mandatory, even if the title includes the namespace prefix. This
            is the preferred syntax when using an already-normalized title
            obtained from api.php or a database dump. WARNING: may produce
            invalid objects if page title isn't in normal form!
          - If the first argument is a Link, create a Page from that link.
            This is the preferred syntax when using a title scraped from
            wikitext, URLs, or another non-normalized source.

        @param source: the source of the page
        @type source: Link, Page (or subclass), or Site
        @param title: normalized title of the page; required if source is a
            Site, ignored otherwise
        @type title: unicode
        @param ns: namespace number; required if source is a Site, ignored
            otherwise
        @type ns: int
        """
        if title is None:
            raise ValueError(u'Title cannot be None.')

        if isinstance(source, pywikibot.site.BaseSite):
            self._link = Link(title, source=source, defaultNamespace=ns)
        elif isinstance(source, Page):
            # copy all of source's attributes to this object
            # without overwriting non-None values
            self.__dict__.update((k, v) for k, v in source.__dict__.items()
                                 if k not in self.__dict__ or
                                 self.__dict__[k] is None)
            if title:
                # overwrite title
                self._link = Link(title, source=source.site,
                                  defaultNamespace=ns)
        elif isinstance(source, Link):
            self._link = source
        else:
            raise pywikibot.Error(
                "Invalid argument type '%s' in Page constructor: %s"
                % (type(source), source))
        self._rev_cache = None

    @property
    def _revision_cache(self):
        """Lazy load revision cache, in case the title is not already known."""
        if not self._rev_cache:
            self._rev_cache = _RevisionCache.get_cache(self)
        return self._rev_cache

    @property
    def site(self):
        """Return the Site object for the wiki on which this Page resides."""
        return self._link.site

    def version(self):
        """
        Return MediaWiki version number of the page site.

        This is needed to use @need_version() decorator for methods of
        Page objects.
        """
        return self.site.version()

    @property
    def image_repository(self):
        """Return the Site object for the image repository."""
        return self.site.image_repository()

    @property
    def data_repository(self):
        """Return the Site object for the data repository."""
        return self.site.data_repository()

    def namespace(self):
        """
        Return the number of the namespace of the page.

        @return: namespace of the page
        @rtype: int
        """
        return self._link.namespace

    @property
    def _namespace_obj(self):
        """Return the namespace object of the page."""
        # TODO: T104864: Temporary until Page.namespace() is consistent
        return self.site.namespaces[self.namespace()]

    @property
    def content_model(self):
        """
        Return the content model for this page.

        If it cannot be reliably determined via the API,
        None is returned.
        """
        # TODO: T102735: Add a sane default of 'wikitext' and others for <1.21
        if not hasattr(self, '_contentmodel'):
            self.site.loadpageinfo(self)
        return self._contentmodel

    @property
    def depth(self):
        """Return the depth/subpage level of the page."""
        if not hasattr(self, '_depth'):
            # Check if the namespace allows subpages
            if self._namespace_obj.subpages:
                _depth = self.title().count('/')
            else:
                # Does not allow subpages, which means depth is always 0
                _depth = 0

        return _depth

    @property
    def pageid(self):
        """
        Return pageid of the page.

        @return: pageid or 0 if page does not exist
        @rtype: int
        """
        if not hasattr(self, '_pageid'):
            self.site.loadpageinfo(self)
        return self._pageid

    @deprecated_args(decode=None, savetitle="asUrl")
    def title(self, underscore=False, withNamespace=True,
              withSection=True, asUrl=False, asLink=False,
              allowInterwiki=True, forceInterwiki=False, textlink=False,
              as_filename=False, insite=None):
        """
        Return the title of this Page, as a Unicode string.

        @param underscore: (not used with asLink) if true, replace all ' '
            characters with '_'
        @param withNamespace: if false, omit the namespace prefix. If this
            option is false and used together with asLink return a labeled
            link like [[link|label]]
        @param withSection: if false, omit the section
        @param asUrl: (not used with asLink) if true, quote title as if in an
            URL
        @param asLink: if true, return the title in the form of a wikilink
        @param allowInterwiki: (only used if asLink is true) if true, format
            the link as an interwiki link if necessary
        @param forceInterwiki: (only used if asLink is true) if true, always
            format the link as an interwiki link
        @param textlink: (only used if asLink is true) if true, place a ':'
            before Category: and Image: links
        @param as_filename: (not used with asLink) if true, replace any
            characters that are unsafe in filenames
        @param insite: (only used if asLink is true) a site object where the
            title is to be shown. default is the current family/lang given by
            -family and -lang option i.e. config.family and config.mylang
        @rtype: unicode
        """
        title = self._link.canonical_title()
        label = self._link.title
        if withSection and self._link.section:
            section = u"#" + self._link.section
        else:
            section = u''
        if asLink:
            if insite:
                target_code = insite.code
                target_family = insite.family.name
            else:
                target_code = config.mylang
                target_family = config.family
            if forceInterwiki or \
               (allowInterwiki and
                (self.site.family.name != target_family or
                 self.site.code != target_code)):
                if self.site.family.name != target_family \
                   and self.site.family.name != self.site.code:
                    title = u'%s:%s:%s' % (self.site.family.name,
                                           self.site.code,
                                           title)
                else:
                    # use this form for sites like commons, where the
                    # code is the same as the family name
                    title = u'%s:%s' % (self.site.code, title)
            elif textlink and (self.is_filepage() or self.is_categorypage()):
                title = u':%s' % title
            elif self.namespace() == 0 and not section:
                withNamespace = True
            if withNamespace:
                return u'[[%s%s]]' % (title, section)
            else:
                return u'[[%s%s|%s]]' % (title, section, label)
        if not withNamespace and self.namespace() != 0:
            title = label + section
        else:
            title += section
        if underscore or asUrl:
            title = title.replace(u' ', u'_')
        if asUrl:
            encodedTitle = title.encode(self.site.encoding())
            title = quote_from_bytes(encodedTitle)
        if as_filename:
            # Replace characters that are not possible in file names on some
            # systems.
            # Spaces are possible on most systems, but are bad for URLs.
            for forbidden in ':*?/\\ ':
                title = title.replace(forbidden, '_')
        return title

    @remove_last_args(('decode', 'underscore'))
    def section(self):
        """
        Return the name of the section this Page refers to.

        The section is the part of the title following a '#' character, if
        any. If no section is present, return None.

        @rtype: unicode
        """
        return self._link.section

    def __unicode__(self):
        """Return a unicode string representation."""
        return self.title(asLink=True, forceInterwiki=True)

    def __repr__(self):
        """Return a more complete string representation."""
        if not PY2:
            title = repr(self.title())
        else:
            try:
                title = self.title().encode(config.console_encoding)
            except UnicodeEncodeError:
                # okay console encoding didn't work, at least try something
                title = self.title().encode('unicode_escape')
        return str('{0}({1})').format(self.__class__.__name__, title)

    def _cmpkey(self):
        """
        Key for comparison of Page objects.

        Page objects are "equal" if and only if they are on the same site
        and have the same normalized title, including section if any.

        Page objects are sortable by site, namespace then title.
        """
        return (self.site, self.namespace(), self.title())

    def __hash__(self):
        """
        A stable identifier to be used as a key in hash-tables.

        This relies on the fact that the string
        representation of an instance can not change after the construction.
        """
        return hash(unicode(self))

    def full_url(self):
        """Return the full URL."""
        return self.site.base_url(self.site.article_path +
                                  self.title(asUrl=True))

    def autoFormat(self):
        """
        Return L{date.getAutoFormat} dictName and value, if any.

        Value can be a year, date, etc., and dictName is 'YearBC',
        'Year_December', or another dictionary name. Please note that two
        entries may have exactly the same autoFormat, but be in two
        different namespaces, as some sites have categories with the
        same names. Regular titles return (None, None).
        """
        if not hasattr(self, '_autoFormat'):
            from pywikibot import date
            self._autoFormat = date.getAutoFormat(
                self.site.code,
                self.title(withNamespace=False)
            )
        return self._autoFormat

    def isAutoTitle(self):
        """Return True if title of this Page is in the autoFormat dictionary."""
        return self.autoFormat()[0] is not None

    @deprecated_args(throttle=None,
                     change_edit_time=None,
                     expandtemplates=None)
    def get(self, force=False, get_redirect=False, sysop=False):
        """
        Return the wiki-text of the page.

        This will retrieve the page from the server if it has not been
        retrieved yet, or if force is True. This can raise the following
        exceptions that should be caught by the calling code:

        @exception NoPage:         The page does not exist
        @exception IsRedirectPage: The page is a redirect. The argument of the
                                   exception is the title of the page it
                                   redirects to.
        @exception SectionError:   The section does not exist on a page with
                                   a # link

        @param force:           reload all page attributes, including errors.
        @param get_redirect:    return the redirect text, do not follow the
                                redirect, do not raise an exception.
        @param sysop:           if the user has a sysop account, use it to
                                retrieve this page

        @rtype: unicode
        """
        if force:
            del self.latest_revision_id
        try:
            self._getInternals(sysop)
        except pywikibot.IsRedirectPage:
            if not get_redirect:
                raise

        return self.latest_revision.text

    def _latest_cached_revision(self):
        """Get the latest revision if cached and has text, otherwise None."""
        if (hasattr(self, '_revid') and self._revid in self._revision_cache and
                self._revision_cache[self._revid].text is not None):
            return self._revision_cache[self._revid]
        else:
            return None

    def _getInternals(self, sysop):
        """
        Helper function for get().

        Stores latest revision in self if it doesn't contain it, doesn't think.
        * Raises exceptions from previous runs.
        * Stores new exceptions in _getexception and raises them.
        """
        # Raise exceptions from previous runs
        if hasattr(self, '_getexception'):
            raise self._getexception

        # If not already stored, fetch revision
        if not hasattr(self, '_revid'):
            if not self.exists():
                raise pywikibot.NoPage(self)
            self._revid = list(self._revision_cache.get_revisions(total=1, content=True))[0].revid
        self._text = self._revision_cache[self._revid].text

        # self._isredir is set by exists()
        if self._isredir:
            self._getexception = pywikibot.IsRedirectPage(self)
            raise self._getexception

    @deprecated_args(throttle=None, change_edit_time=None)
    def getOldVersion(self, oldid, force=False, get_redirect=False,
                      sysop=False):
        """
        Return text of an old revision of this page; same options as get().

        @param oldid: The revid of the revision desired.
        @rtype: unicode
        """
        # TODO: what about redirects, errors?
        return self._revision_cache[oldid].text

    def permalink(self, oldid=None, percent_encoded=True):
        """Return the permalink URL of an old revision of this page.

        @param oldid: The revid of the revision desired.
        @rtype: unicode
        """
        if percent_encoded:
            title = self.title(asUrl=True)
        else:
            title = self.title(asUrl=False).replace(' ', '_')
        return "//%s%s/index.php?title=%s&oldid=%s" \
               % (self.site.hostname(),
                  self.site.scriptpath(),
                  title,
                  (oldid if oldid is not None else self.latest_revision_id))

    @property
    def latest_revision_id(self):
        """Return the current revision id for this page."""
        if not hasattr(self, '_revid'):
            self.revisions(self)
        return self._revid

    @latest_revision_id.deleter
    def latest_revision_id(self):
        """
        Remove the latest revision id set for this Page.

        All internal cached values specifically for the latest revision
        of this page are cleared.

        The following cached values are not cleared:
        - text property
        - page properties, and page coordinates
        - lastNonBotUser
        - isDisambig and isCategoryRedirect status
        - langlinks, templates and deleted revisions
        """
        # When forcing, we retry the page no matter what:
        # * Old exceptions do not apply any more
        # * Deleting _revid to force reload
        # * Deleting _redirtarget, that info is now obsolete.
        for attr in ['_redirtarget', '_getexception', '_revid']:
            if hasattr(self, attr):
                delattr(self, attr)

    @latest_revision_id.setter
    def latest_revision_id(self, value):
        """Set the latest revision for this Page."""
        del self.latest_revision_id
        self._revid = value

    @deprecated('latest_revision_id')
    def latestRevision(self):
        """Return the current revision id for this page."""
        return self.latest_revision_id

    @deprecated('latest_revision_id')
    def pageAPInfo(self):
        """Return the current revision id for this page."""
        if self.isRedirectPage():
            raise pywikibot.IsRedirectPage(self)
        return self.latest_revision_id

    @property
    def latest_revision(self):
        """Return the current revision for this page."""
        rev = self._latest_cached_revision()
        if rev is not None:
            return rev
        return next(self.revisions(content=True, total=1))

    @property
    def text(self):
        """
        Return the current (edited) wikitext, loading it if necessary.

        @return: text of the page
        @rtype: unicode
        """
        if not hasattr(self, '_text') or self._text is None:
            try:
                self._text = self.get(get_redirect=True)
            except pywikibot.NoPage:
                # TODO: what other exceptions might be returned?
                self._text = u""
        return self._text

    @text.setter
    def text(self, value):
        """
        Update the current (edited) wikitext.

        @param value: New value or None
        @param value: basestring
        """
        self._text = None if value is None else unicode(value)
        if hasattr(self, '_raw_extracted_templates'):
            del self._raw_extracted_templates

    @text.deleter
    def text(self):
        """Delete the current (edited) wikitext."""
        if hasattr(self, "_text"):
            del self._text
        if hasattr(self, '_expanded_text'):
            del self._expanded_text
        if hasattr(self, '_raw_extracted_templates'):
            del self._raw_extracted_templates

    def preloadText(self):
        """
        The text returned by EditFormPreloadText.

        See API module "info".

        Application: on Wikisource wikis, text can be preloaded even if
        a page does not exist, if an Index page is present.

        @rtype: unicode
        """
        self.site.loadpageinfo(self, preload=True)
        return self._preloadedtext

    def _get_parsed_page(self):
        """Retrieve parsed text (via action=parse) and cache it."""
        # Get (cached) parsed text.
        if not hasattr(self, '_parsed_text'):
            self._parsed_text = self.site.get_parsed_page(self)
        return self._parsed_text

    def properties(self, force=False):
        """
        Return the properties of the page.

        @param force: force updating from the live site

        @rtype: dict
        """
        if not hasattr(self, '_pageprops') or force:
            self._pageprops = {}  # page may not have pageprops (see bug T56868)
            self.site.loadpageprops(self)
        return self._pageprops

    def defaultsort(self, force=False):
        """
        Extract value of the {{DEFAULTSORT:}} magic word from the page.

        @param force: force updating from the live site

        @rtype: unicode or None
        """
        return self.properties(force=force).get('defaultsort')

    @deprecate_arg('refresh', 'force')
    def expand_text(self, force=False, includecomments=False):
        """Return the page text with all templates and parser words expanded.

        @param force: force updating from the live site
        @param includecomments: Also strip comments if includecomments
            parameter is not True.

        @rtype unicode or None
        """
        if not hasattr(self, '_expanded_text') or (
                self._expanded_text is None) or force:
            if not self.text:
                self._expanded_text = ''
                return ''

            self._expanded_text = self.site.expand_text(
                self.text,
                title=self.title(withSection=False),
                includecomments=includecomments)
        return self._expanded_text

    def userName(self):
        """
        Return name or IP address of last user to edit page.

        @rtype: unicode
        """
        return self.latest_revision.user

    def isIpEdit(self):
        """
        Return True if last editor was unregistered.

        @rtype: bool
        """
        return self.latest_revision.anon

    def lastNonBotUser(self):
        """
        Return name or IP address of last human/non-bot user to edit page.

        Determine the most recent human editor out of the last revisions.
        If it was not able to retrieve a human user, returns None.

        If the edit was done by a bot which is no longer flagged as 'bot',
        i.e. which is not returned by Site.botusers(), it will be returned
        as a non-bot edit.

        @rtype: unicode
        """
        if hasattr(self, '_lastNonBotUser'):
            return self._lastNonBotUser

        self._lastNonBotUser = None
        for entry in self.revisions():
            if entry.user and (not self.site.isBot(entry.user)):
                self._lastNonBotUser = entry.user
                break

        return self._lastNonBotUser

    @remove_last_args(('datetime', ))
    def editTime(self):
        """Return timestamp of last revision to page.

        @rtype: pywikibot.Timestamp
        """
        return self.latest_revision.timestamp

    @property
    @deprecated('latest_revision.parent_id (0 instead of -1 when no parent)')
    def previous_revision_id(self):
        """
        Return the revision id for the previous revision of this Page.

        If the page has only one revision, it shall return -1.

        @rtype: long

        @raise AssertionError: Use on MediaWiki prior to v1.16.
        """
        return self.latest_revision.parent_id or -1

    @deprecated('latest_revision.parent_id (0 instead of -1 when no parent)')
    def previousRevision(self):
        """
        Return the revision id for the previous revision.

        DEPRECATED: Use latest_revision.parent_id instead.

        @rtype: long

        @raise AssertionError: Use on MediaWiki prior to v1.16.
        """
        return self.latest_revision.parent_id or -1

    def exists(self):
        """Return True if page exists on the wiki, even if it's a redirect.

        If the title includes a section, return False if this section isn't
        found.

        @rtype: bool
        """
        return self.site.page_exists(self)

    @property
    def oldest_revision(self):
        """
        Return the first revision of this page.

        @rtype: L{Revision}
        """
        return next(self._revision_cache.get_revisions(reverse=True, total=1))

    def isRedirectPage(self):
        """Return True if this is a redirect, False if not or not existing."""
        return self.site.page_isredirect(self)

    def isStaticRedirect(self, force=False):
        """
        Determine whether the page is a static redirect.

        A static redirect must be a valid redirect, and contain the magic word
        __STATICREDIRECT__.

        @param force: Bypass local caching
        @type force: bool

        @rtype: bool
        """
        found = False
        if self.isRedirectPage():
            staticKeys = self.site.getmagicwords('staticredirect')
            text = self.get(get_redirect=True, force=force)
            if staticKeys:
                for key in staticKeys:
                    if key in text:
                        found = True
                        break
        return found

    def isCategoryRedirect(self):
        """
        Return True if this is a category redirect page, False otherwise.

        @rtype: bool
        """
        if not self.is_categorypage():
            return False
        if not hasattr(self, "_catredirect"):
            catredirs = self.site._category_redirects()
            for (template, args) in self.templatesWithParams():
                if template.title(withNamespace=False) in catredirs:
                    # Get target (first template argument)
                    try:
                        p = pywikibot.Page(self.site, args[0].strip(), ns=14)
                        if p.namespace() == 14:
                            self._catredirect = p.title()
                        else:
                            pywikibot.warning(
                                u"Target %s on %s is not a category"
                                % (p.title(asLink=True),
                                   self.title(asLink=True)))
                            self._catredirect = False
                    except IndexError:
                        pywikibot.warning(
                            u"No target for category redirect on %s"
                            % self.title(asLink=True))
                        self._catredirect = False
                    break
            else:
                self._catredirect = False
        return bool(self._catredirect)

    def getCategoryRedirectTarget(self):
        """
        If this is a category redirect, return the target category title.

        @rtype: Category
        """
        if self.isCategoryRedirect():
            return Category(Link(self._catredirect, self.site))
        raise pywikibot.IsNotRedirectPage(self)

    @deprecated("interwiki.page_empty_check(page)")
    def isEmpty(self):
        """
        Return True if the page text has less than 4 characters.

        Character count ignores language links and category links.
        Can raise the same exceptions as get().

        @rtype: bool
        """
        txt = self.get()
        txt = textlib.removeLanguageLinks(txt, site=self.site)
        txt = textlib.removeCategoryLinks(txt, site=self.site)
        return len(txt) < 4

    def isTalkPage(self):
        """Return True if this page is in any talk namespace."""
        ns = self.namespace()
        return ns >= 0 and ns % 2 == 1

    def toggleTalkPage(self):
        """
        Return other member of the article-talk page pair for this Page.

        If self is a talk page, returns the associated content page;
        otherwise, returns the associated talk page. The returned page need
        not actually exist on the wiki.

        @return: Page or None if self is a special page.
        @rtype: Page or None
        """
        ns = self.namespace()
        if ns < 0:  # Special page
            return
        if self.isTalkPage():
            if self.namespace() == 1:
                return Page(self.site, self.title(withNamespace=False))
            else:
                return Page(self.site,
                            "%s:%s" % (self.site.namespace(ns - 1),
                                       self.title(withNamespace=False)))
        else:
            return Page(self.site,
                        "%s:%s" % (self.site.namespace(ns + 1),
                                   self.title(withNamespace=False)))

    def is_categorypage(self):
        """Return True if the page is a Category, False otherwise."""
        return self.namespace() == 14

    @deprecated('is_categorypage')
    def isCategory(self):
        """DEPRECATED: use is_categorypage instead."""
        return self.is_categorypage()

    def is_filepage(self):
        """Return True if this is an file description page, False otherwise."""
        return self.namespace() == 6

    @deprecated('is_filepage')
    def isImage(self):
        """DEPRECATED: use is_filepage instead."""
        return self.is_filepage()

    @remove_last_args(('get_Index', ))
    def isDisambig(self):
        """
        Return True if this is a disambiguation page, False otherwise.

        By default, it uses the the Disambiguator extension's result. The
        identification relies on the presense of the __DISAMBIG__ magic word
        which may also be transcluded.

        If the Disambiguator extension isn't activated for the given site,
        the identification relies on the presence of specific templates.
        First load a list of template names from the Family file;
        if the value in the Family file is None or no entry was made, look for
        the list on [[MediaWiki:Disambiguationspage]]. If this page does not
        exist, take the MediaWiki message. 'Template:Disambig' is always
        assumed to be default, and will be appended regardless of its existence.

        @rtype: bool
        """
        if self.site.has_extension('Disambiguator'):
            # If the Disambiguator extension is loaded, use it
            return 'disambiguation' in self.properties()

        if not hasattr(self.site, "_disambigtemplates"):
            try:
                default = set(self.site.family.disambig('_default'))
            except KeyError:
                default = set([u'Disambig'])
            try:
                distl = self.site.family.disambig(self.site.code,
                                                  fallback=False)
            except KeyError:
                distl = None
            if distl is None:
                disambigpages = Page(self.site,
                                     "MediaWiki:Disambiguationspage")
                if disambigpages.exists():
                    disambigs = set(link.title(withNamespace=False)
                                    for link in disambigpages.linkedPages()
                                    if link.namespace() == 10)
                elif self.site.has_mediawiki_message('disambiguationspage'):
                    message = self.site.mediawiki_message(
                        'disambiguationspage').split(':', 1)[1]
                    # add the default template(s) for default mw message
                    # only
                    disambigs = set([first_upper(message)]) | default
                else:
                    disambigs = default
                self.site._disambigtemplates = disambigs
            else:
                # Normalize template capitalization
                self.site._disambigtemplates = set(
                    first_upper(t) for t in distl
                )
        templates = set(tl.title(withNamespace=False)
                        for tl in self.templates())
        disambigs = set()
        # always use cached disambig templates
        disambigs.update(self.site._disambigtemplates)
        # see if any template on this page is in the set of disambigs
        disambigInPage = disambigs.intersection(templates)
        return self.namespace() != 10 and len(disambigInPage) > 0

    @deprecated_args(step=None)
    def getReferences(self, follow_redirects=True, withTemplateInclusion=True,
                      onlyTemplateInclusion=False, redirectsOnly=False,
                      namespaces=None, total=None, content=False):
        """
        Return an iterator all pages that refer to or embed the page.

        If you need a full list of referring pages, use
        C{pages = list(s.getReferences())}

        @param follow_redirects: if True, also iterate pages that link to a
            redirect pointing to the page.
        @param withTemplateInclusion: if True, also iterate pages where self
            is used as a template.
        @param onlyTemplateInclusion: if True, only iterate pages where self
            is used as a template.
        @param redirectsOnly: if True, only iterate redirects to self.
        @param namespaces: only iterate pages in these namespaces
        @param total: iterate no more than this number of pages in total
        @param content: if True, retrieve the content of the current version
            of each referring page (default False)
        """
        # N.B.: this method intentionally overlaps with backlinks() and
        # embeddedin(). Depending on the interface, it may be more efficient
        # to implement those methods in the site interface and then combine
        # the results for this method, or to implement this method and then
        # split up the results for the others.
        return self.site.pagereferences(
            self,
            followRedirects=follow_redirects,
            filterRedirects=redirectsOnly,
            withTemplateInclusion=withTemplateInclusion,
            onlyTemplateInclusion=onlyTemplateInclusion,
            namespaces=namespaces,
            total=total,
            content=content
        )

    @deprecated_args(step=None)
    def backlinks(self, followRedirects=True, filterRedirects=None,
                  namespaces=None, total=None, content=False):
        """
        Return an iterator for pages that link to this page.

        @param followRedirects: if True, also iterate pages that link to a
            redirect pointing to the page.
        @param filterRedirects: if True, only iterate redirects; if False,
            omit redirects; if None, do not filter
        @param namespaces: only iterate pages in these namespaces
        @param total: iterate no more than this number of pages in total
        @param content: if True, retrieve the content of the current version
            of each referring page (default False)
        """
        return self.site.pagebacklinks(
            self,
            followRedirects=followRedirects,
            filterRedirects=filterRedirects,
            namespaces=namespaces,
            total=total,
            content=content
        )

    @deprecated_args(step=None)
    def embeddedin(self, filter_redirects=None, namespaces=None,
                   total=None, content=False):
        """
        Return an iterator for pages that embed this page as a template.

        @param filter_redirects: if True, only iterate redirects; if False,
            omit redirects; if None, do not filter
        @param namespaces: only iterate pages in these namespaces
        @param total: iterate no more than this number of pages in total
        @param content: if True, retrieve the content of the current version
            of each embedding page (default False)
        """
        return self.site.page_embeddedin(
            self,
            filterRedirects=filter_redirects,
            namespaces=namespaces,
            total=total,
            content=content
        )

    def protection(self):
        """
        Return a dictionary reflecting page protections.

        @rtype: dict
        """
        return self.site.page_restrictions(self)

    def applicable_protections(self):
        """
        Return the protection types allowed for that page.

        If the page doesn't exists it only returns "create". Otherwise it
        returns all protection types provided by the site, except "create".
        It also removes "upload" if that page is not in the File namespace.

        It is possible, that it returns an empty set, but only if original
        protection types were removed.

        @return: set of unicode
        @rtype: set
        """
        # New API since commit 32083235eb332c419df2063cf966b3400be7ee8a
        if MediaWikiVersion(self.site.version()) >= MediaWikiVersion('1.25wmf14'):
            self.site.loadpageinfo(self)
            return self._applicable_protections

        p_types = set(self.site.protection_types())
        if not self.exists():
            return set(['create']) if 'create' in p_types else set()
        else:
            p_types.remove('create')  # no existing page allows that
            if not self.is_filepage():  # only file pages allow upload
                p_types.remove('upload')
            return p_types

    def canBeEdited(self):
        """
        Determine whether the page may be edited.

        This returns True if and only if:
          - page is unprotected, and bot has an account for this site, or
          - page is protected, and bot has a sysop account for this site.

        @rtype: bool
        """
        return self.site.page_can_be_edited(self)

    def botMayEdit(self):
        """
        Determine whether the active bot is allowed to edit the page.

        This will be True if the page doesn't contain {{bots}} or
        {{nobots}}, or it contains them and the active bot is allowed to
        edit this page. (This method is only useful on those sites that
        recognize the bot-exclusion protocol; on other sites, it will always
        return True.)

        The framework enforces this restriction by default. It is possible
        to override this by setting ignore_bot_templates=True in
        user-config.py, or using page.put(force=True).

        @rtype: bool
        """
        # TODO: move this to Site object?

        # FIXME: templatesWithParams is defined in Page only.
        if not hasattr(self, 'templatesWithParams'):
            return True

        if config.ignore_bot_templates:  # Check the "master ignore switch"
            return True
        username = self.site.user()
        try:
            templates = self.templatesWithParams()
        except (pywikibot.NoPage,
                pywikibot.IsRedirectPage,
                pywikibot.SectionError):
            return True

        # go through all templates and look for any restriction
        # multiple bots/nobots templates are allowed
        for template in templates:
            title = template[0].title(withNamespace=False)
            if title == 'Nobots':
                if len(template[1]) == 0:
                    return False
                else:
                    bots = template[1][0].split(',')
                    if 'all' in bots or pywikibot.calledModuleName() in bots \
                       or username in bots:
                        return False
            elif title == 'Bots':
                if len(template[1]) == 0:
                    return True
                else:
                    (ttype, bots) = template[1][0].split('=', 1)
                    bots = bots.split(',')
                    if ttype == 'allow':
                        return 'all' in bots or username in bots
                    if ttype == 'deny':
                        return not ('all' in bots or username in bots)
                    if ttype == 'allowscript':
                        return 'all' in bots or pywikibot.calledModuleName() in bots
                    if ttype == 'denyscript':
                        return not ('all' in bots or pywikibot.calledModuleName() in bots)
        # no restricting template found
        return True

    @deprecate_arg('async', 'asynchronous')  # T106230
    @deprecated_args(comment='summary', sysop=None)
    def save(self, summary=None, watch=None, minor=True, botflag=None,
             force=False, asynchronous=False, callback=None,
             apply_cosmetic_changes=None, quiet=False, **kwargs):
        """
        Save the current contents of page's text to the wiki.

        @param summary: The edit summary for the modification (optional, but
            most wikis strongly encourage its use)
        @type summary: unicode
        @param watch: Specify how the watchlist is affected by this edit, set
            to one of "watch", "unwatch", "preferences", "nochange":
            * watch: add the page to the watchlist
            * unwatch: remove the page from the watchlist
            * preferences: use the preference settings (Default)
            * nochange: don't change the watchlist
            If None (default), follow bot account's default settings

            For backward compatibility watch parameter may also be boolean:
            if True, add or if False, remove this Page to/from bot
            user's watchlist.
        @type watch: string, bool (deprecated) or None
        @param minor: if True, mark this edit as minor
        @type minor: bool
        @param botflag: if True, mark this edit as made by a bot (default:
            True if user has bot status, False if not)
        @param force: if True, ignore botMayEdit() setting
        @type force: bool
        @param asynchronous: if True, launch a separate thread to save
            asynchronously
        @param callback: a callable object that will be called after the
            page put operation. This object must take two arguments: (1) a
            Page object, and (2) an exception instance, which will be None
            if the page was saved successfully. The callback is intended for
            use by bots that need to keep track of which saves were
            successful.
        @param apply_cosmetic_changes: Overwrites the cosmetic_changes
            configuration value to this value unless it's None.
        @type apply_cosmetic_changes: bool or None
        @param quiet: enable/disable successful save operation message;
            defaults to False.
            In asynchronous mode, if True, it is up to the calling bot to
            manage the output e.g. via callback.
        @type quiet: bool
        """
        if not summary:
            summary = config.default_edit_summary
        if watch is True:
            watch = 'watch'
        elif watch is False:
            watch = 'unwatch'
        if not force and not self.botMayEdit():
            raise pywikibot.OtherPageSaveError(
                self, "Editing restricted by {{bots}} template")
        self._save(summary=summary, watch=watch, minor=minor, botflag=botflag,
                   asynchronous=asynchronous, callback=callback,
                   cc=apply_cosmetic_changes, quiet=quiet, **kwargs)

    @allow_asynchronous
    def _save(self, summary=None, watch=None, minor=True, botflag=None,
              cc=None, quiet=False, **kwargs):
        """Helper function for save()."""
        link = self.title(asLink=True)
        if cc or cc is None and config.cosmetic_changes:
            summary = self._cosmetic_changes_hook(summary)

        done = self.site.editpage(self, summary=summary, minor=minor,
                                  watch=watch, bot=botflag, **kwargs)
        if not done:
            if not quiet:
                pywikibot.warning('Page %s not saved' % link)
            raise pywikibot.PageNotSaved(self)
        if not quiet:
            pywikibot.output('Page %s saved' % link)

    def _cosmetic_changes_hook(self, summary):
        """The cosmetic changes hook.

        @param summary: The current edit summary.
        @type summary: str
        @return: Modified edit summary if cosmetic changes has been done,
            else the old edit summary.
        @rtype: str
        """
        if self.isTalkPage() or \
           pywikibot.calledModuleName() in config.cosmetic_changes_deny_script:
            return summary
        family = self.site.family.name
        if config.cosmetic_changes_mylang_only:
            cc = ((family == config.family and
                   self.site.lang == config.mylang) or
                  family in list(config.cosmetic_changes_enable.keys()) and
                  self.site.lang in config.cosmetic_changes_enable[family])
        else:
            cc = True
        cc = (cc and not
              (family in list(config.cosmetic_changes_disable.keys()) and
               self.site.lang in config.cosmetic_changes_disable[family]))
        if not cc:
            return summary

        old = self.text
        pywikibot.log(u'Cosmetic changes for %s-%s enabled.'
                      % (family, self.site.lang))
        # cc depends on page directly and via several other imports
        from pywikibot.cosmetic_changes import (
            CANCEL_MATCH, CosmeticChangesToolkit)  # noqa
        ccToolkit = CosmeticChangesToolkit(self.site,
                                           namespace=self.namespace(),
                                           pageTitle=self.title(),
                                           ignore=CANCEL_MATCH)
        self.text = ccToolkit.change(old)
        if summary and old.strip().replace(
                '\r\n', '\n') != self.text.strip().replace('\r\n', '\n'):
            from pywikibot import i18n
            summary += i18n.twtranslate(self.site, 'cosmetic_changes-append')
        return summary

    @deprecate_arg('async', 'asynchronous')  # T106230
    @deprecated_args(comment='summary')
    def put(self, newtext, summary=u'', watchArticle=None, minorEdit=True,
            botflag=None, force=False, asynchronous=False, callback=None, **kwargs):
        """
        Save the page with the contents of the first argument as the text.

        This method is maintained primarily for backwards-compatibility.
        For new code, using Page.save() is preferred. See save() method
        docs for all parameters not listed here.

        @param newtext: The complete text of the revised page.
        @type newtext: unicode

        """
        self.text = newtext
        self.save(summary=summary, watch=watchArticle, minor=minorEdit,
                  botflag=botflag, force=force, asynchronous=asynchronous,
                  callback=callback, **kwargs)

    @deprecated_args(comment='summary')
    def put_async(self, newtext, summary=u'', watchArticle=None,
                  minorEdit=True, botflag=None, force=False, callback=None,
                  **kwargs):
        """
        Put page on queue to be saved to wiki asynchronously.

        Asynchronous version of put (takes the same arguments), which places
        pages on a queue to be saved by a daemon thread. All arguments are
        the same as for .put(). This version is maintained solely for
        backwards-compatibility.
        """
        self.put(newtext, summary=summary, watchArticle=watchArticle,
                 minorEdit=minorEdit, botflag=botflag, force=force,
                 asynchronous=True, callback=callback, **kwargs)

    def watch(self, unwatch=False):
        """
        Add or remove this page to/from bot account's watchlist.

        @param unwatch: True to unwatch, False (default) to watch.
        @type unwatch: bool

        @return: True if successful, False otherwise.
        @rtype: bool
        """
        return self.site.watch(self, unwatch)

    def clear_cache(self):
        """Clear the cached attributes of the page."""
        for attr in self._cache_attrs:
            try:
                delattr(self, attr)
            except AttributeError:
                pass

    def purge(self, **kwargs):
        """
        Purge the server's cache for this page.

        @rtype: bool
        """
        self.clear_cache()
        return self.site.purgepages([self], **kwargs)

    def touch(self, callback=None, botflag=False, **kwargs):
        """
        Make a touch edit for this page.

        See save() method docs for all parameters.
        The following parameters will be overridden by this method:
        - summary, watch, minor, force, asynchronous

        Parameter botflag is False by default.

        minor and botflag parameters are set to False which prevents hiding
        the edit when it becomes a real edit due to a bug.
        """
        if self.exists():
            # ensure always get the page text and not to change it.
            del self.text
            self.save(summary='Pywikibot touch edit', watch='nochange',
                      minor=False, botflag=botflag, force=True,
                      asynchronous=False, callback=callback,
                      apply_cosmetic_changes=False, **kwargs)
        else:
            raise pywikibot.NoPage(self)

    @deprecated_args(step=None)
    def linkedPages(self, namespaces=None, total=None,
                    content=False):
        """
        Iterate Pages that this Page links to.

        Only returns pages from "normal" internal links. Image and category
        links are omitted unless prefixed with ":". Embedded templates are
        omitted (but links within them are returned). All interwiki and
        external links are omitted.

        @param namespaces: only iterate links in these namespaces
        @param namespaces: int, or list of ints
        @param total: iterate no more than this number of pages in total
        @type total: int
        @param content: if True, retrieve the content of the current version
            of each linked page (default False)
        @type content: bool

        @return: a generator that yields Page objects.
        @rtype: generator
        """
        return self.site.pagelinks(self, namespaces=namespaces,
                                   total=total, content=content)

    def interwiki(self, expand=True):
        """
        Iterate interwiki links in the page text, excluding language links.

        @param expand: if True (default), include interwiki links found in
            templates transcluded onto this page; if False, only iterate
            interwiki links found in this page's own wikitext
        @type expand: bool

        @return: a generator that yields Link objects
        @rtype: generator
        """
        # This function does not exist in the API, so it has to be
        # implemented by screen-scraping
        if expand:
            text = self.expand_text()
        else:
            text = self.text
        for linkmatch in pywikibot.link_regex.finditer(
                textlib.removeDisabledParts(text)):
            linktitle = linkmatch.group("title")
            link = Link(linktitle, self.site)
            # only yield links that are to a different site and that
            # are not language links
            try:
                if link.site != self.site:
                    if linktitle.lstrip().startswith(":"):
                        # initial ":" indicates not a language link
                        yield link
                    elif link.site.family != self.site.family:
                        # link to a different family is not a language link
                        yield link
            except pywikibot.Error:
                # ignore any links with invalid contents
                continue

    def langlinks(self, include_obsolete=False):
        """
        Return a list of all inter-language Links on this page.

        @param include_obsolete: if true, return even Link objects whose site
                                 is obsolete
        @type include_obsolete: bool

        @return: list of Link objects.
        @rtype: list
        """
        # Note: We preload a list of *all* langlinks, including links to
        # obsolete sites, and store that in self._langlinks. We then filter
        # this list if the method was called with include_obsolete=False
        # (which is the default)
        if not hasattr(self, '_langlinks'):
            self._langlinks = list(self.iterlanglinks(include_obsolete=True))

        if include_obsolete:
            return self._langlinks
        else:
            return [i for i in self._langlinks if not i.site.obsolete]

    @deprecated_args(step=None)
    def iterlanglinks(self, total=None, include_obsolete=False):
        """
        Iterate all inter-language links on this page.

        @param total: iterate no more than this number of pages in total
        @param include_obsolete: if true, yield even Link object whose site
                                 is obsolete
        @type include_obsolete: bool

        @return: a generator that yields Link objects.
        @rtype: generator
        """
        if hasattr(self, '_langlinks'):
            return iter(self.langlinks(include_obsolete=include_obsolete))
        # XXX We might want to fill _langlinks when the Site
        # method is called. If we do this, we'll have to think
        # about what will happen if the generator is not completely
        # iterated upon.
        return self.site.pagelanglinks(self, total=total,
                                       include_obsolete=include_obsolete)

    def data_item(self):
        """
        Convenience function to get the Wikibase item of a page.

        @rtype: ItemPage
        """
        return ItemPage.fromPage(self)

    @deprecate_arg('tllimit', None)
    @deprecated("Page.templates()")
    def getTemplates(self):
        """DEPRECATED. Use templates()."""
        return self.templates()

    def templates(self, content=False):
        """
        Return a list of Page objects for templates used on this Page.

        Template parameters are ignored. This method only returns embedded
        templates, not template pages that happen to be referenced through
        a normal link.

        @param content: if True, retrieve the content of the current version
            of each template (default False)
        @param content: bool
        """
        # Data might have been preloaded
        if not hasattr(self, '_templates'):
            self._templates = list(self.itertemplates(content=content))

        return self._templates

    @deprecated_args(step=None)
    def itertemplates(self, total=None, content=False):
        """
        Iterate Page objects for templates used on this Page.

        Template parameters are ignored. This method only returns embedded
        templates, not template pages that happen to be referenced through
        a normal link.

        @param total: iterate no more than this number of pages in total
        @param content: if True, retrieve the content of the current version
            of each template (default False)
        @param content: bool
        """
        if hasattr(self, '_templates'):
            return iter(self._templates)
        return self.site.pagetemplates(self, total=total, content=content)

    @deprecated_args(followRedirects=None, loose=None, step=None)
    def imagelinks(self, total=None, content=False):
        """
        Iterate FilePage objects for images displayed on this Page.

        @param total: iterate no more than this number of pages in total
        @param content: if True, retrieve the content of the current version
            of each image description page (default False)
        @return: a generator that yields FilePage objects.
        """
        return self.site.pageimages(self, total=total, content=content)

    @deprecated_args(nofollow_redirects=None, get_redirect=None, step=None)
    def categories(self, withSortKey=False, total=None, content=False):
        """
        Iterate categories that the article is in.

        @param withSortKey: if True, include the sort key in each Category.
        @param total: iterate no more than this number of pages in total
        @param content: if True, retrieve the content of the current version
            of each category description page (default False)
        @return: a generator that yields Category objects.
        @rtype: generator
        """
        # FIXME: bug T75561: withSortKey is ignored by Site.pagecategories
        if withSortKey:
            raise NotImplementedError('withSortKey is not implemented')

        return self.site.pagecategories(self, total=total, content=content)

    @deprecated_args(step=None)
    def extlinks(self, total=None):
        """
        Iterate all external URLs (not interwiki links) from this page.

        @param total: iterate no more than this number of pages in total
        @return: a generator that yields unicode objects containing URLs.
        @rtype: generator
        """
        return self.site.page_extlinks(self, total=total)

    def coordinates(self, primary_only=False):
        """
        Return a list of Coordinate objects for points on the page.

        Uses the MediaWiki extension GeoData.

        @param primary_only: Only return the coordinate indicated to be primary
        @return: A list of Coordinate objects
        @rtype: list
        """
        if not hasattr(self, '_coords'):
            self._coords = []
            self.site.loadcoordinfo(self)
        if primary_only:
            return self._coords[0] if len(self._coords) > 0 else None
        else:
            return self._coords

    def getRedirectTarget(self):
        """
        Return a Page object for the target this Page redirects to.

        If this page is not a redirect page, will raise an IsNotRedirectPage
        exception. This method also can raise a NoPage exception.

        @rtype: pywikibot.Page
        """
        return self.site.getredirtarget(self)

    @deprecated('moved_target()')
    def getMovedTarget(self):
        """
        Return a Page object for the target this Page was moved to.

        DEPRECATED: Use Page.moved_target().

        If this page was not moved, it will raise a NoPage exception.
        This method also works if the source was already deleted.

        @rtype: pywikibot.Page
        @raises NoPage: this page was not moved
        """
        try:
            return self.moved_target()
        except pywikibot.NoMoveTarget:
            raise pywikibot.NoPage(self)

    def moved_target(self):
        """
        Return a Page object for the target this Page was moved to.

        If this page was not moved, it will raise a NoMoveTarget exception.
        This method also works if the source was already deleted.

        @rtype: pywikibot.Page
        @raises NoMoveTarget: this page was not moved
        """
        gen = iter(self.site.logevents(logtype='move', page=self, total=1))
        try:
            lastmove = next(gen)
        except StopIteration:
            raise pywikibot.NoMoveTarget(self)
        else:
            return lastmove.target_page

    @deprecated_args(getText='content', reverseOrder='reverse', step=None)
    def revisions(self, reverse=False, total=None, content=False,
                  rollback=False, starttime=None, endtime=None):
        """Generator which loads the version history as Revision instances."""
        if not self.exists():
            raise pywikibot.NoPage(self)
        return self._revision_cache.get_revisions(
            reverse=reverse, total=total, content=content, rollback=rollback,
            starttime=starttime, endtime=endtime,
        )

    # BREAKING CHANGE: in old framework, default value for getVersionHistory
    #                  returned no more than 500 revisions; now, it iterates
    #                  all revisions unless 'total' argument is used
    @deprecated('Page.revisions()')
    @deprecated_args(forceReload=None, revCount='total', step=None,
                     getAll=None, reverseOrder='reverse')
    def getVersionHistory(self, reverse=False, total=None):
        """
        Load the version history page and return history information.

        Return value is a list of tuples, where each tuple represents one
        edit and is built of revision id, edit date/time, user name, and
        edit summary. Starts with the most current revision, unless
        reverse is True.

        @param total: iterate no more than this number of revisions in total
        """
        return [rev.hist_entry()
                for rev in self.revisions(reverse=reverse, total=total)
                ]

    @deprecated_args(forceReload=None, reverseOrder='reverse', step=None)
    def getVersionHistoryTable(self, reverse=False, total=None):
        """Return the version history as a wiki table."""
        result = '{| class="wikitable"\n'
        result += '! oldid || date/time || username || edit summary\n'
        for entry in self.revisions(reverse=reverse, total=total):
            result += '|----\n'
            result += ('| {r.revid} || {r.timestamp} || {r.user} || '
                       '<nowiki>{r.comment}</nowiki>\n'.format(r=entry))
        result += '|}\n'
        return result

    @deprecated("Page.revisions(content=True)")
    @deprecated_args(reverseOrder='reverse', rollback=None, step=None)
    def fullVersionHistory(self, reverse=False, total=None):
        """Iterate previous versions including wikitext.

        Takes same arguments as getVersionHistory.
        """
        return [rev.full_hist_entry()
                for rev in self.revisions(content=True, reverse=reverse,
                                          total=total)
                ]

    @deprecated_args(step=None)
    def contributors(self, total=None, starttime=None, endtime=None):
        """
        Compile contributors of this page with edit counts.

        @param total: iterate no more than this number of revisions in total
        @param starttime: retrieve revisions starting at this Timestamp
        @param endtime: retrieve revisions ending at this Timestamp

        @return: number of edits for each username
        @rtype: L{collections.Counter}
        """
        return Counter(rev.user for rev in
                       self.revisions(total=total,
                                      starttime=starttime, endtime=endtime))

    @deprecated('contributors()')
    @deprecated_args(step=None)
    def contributingUsers(self, total=None):
        """
        Return a set of usernames (or IPs) of users who edited this page.

        @param total: iterate no more than this number of revisions in total

        @rtype: set
        """
        return self.contributors(total=total).keys()

    def revision_count(self, contributors=None):
        """
        Determine number of edits from a set of contributors.

        @param contributors: contributor usernames
        @type contributors: iterable of str

        @return: number of edits for all provided usernames
        @rtype: int
        """
        if not contributors:
            return len(list(self.revisions()))

        cnt = self.contributors()
        return sum(cnt[username] for username in contributors)

    @deprecated('oldest_revision')
    def getCreator(self):
        """
        Get the first revision of the page.

        DEPRECATED: Use Page.oldest_revision.

        @rtype: tuple(username, Timestamp)
        """
        result = self.oldest_revision
        return result.user, unicode(result.timestamp.isoformat())

    @deprecated('contributors() or revisions()')
    @deprecated_args(limit="total")
    def getLatestEditors(self, total=1):
        """
        Get a list of revision informations of the last total edits.

        DEPRECATED: Use Page.revisions.

        @param total: iterate no more than this number of revisions in total
        @return: list of dict, each dict containing the username and Timestamp
        @rtype: list
        """
        return [{'user': rev.user, 'timestamp': unicode(rev.timestamp.isoformat())}
                for rev in self.revisions(total=total)]

    def merge_history(self, dest, timestamp=None, reason=None):
        """
        Merge revisions from this page into another page.

        See L{APISite.merge_history} for details.

        @param dest: Destination page to which revisions will be merged
        @type dest: pywikibot.Page
        @param timestamp: Revisions from this page dating up to this timestamp
            will be merged into the destination page (if not given or False,
            all revisions will be merged)
        @type timestamp: pywikibot.Timestamp
        @param reason: Optional reason for the history merge
        @type reason: str
        """
        self.site.merge_history(self, dest, timestamp, reason)

    @deprecate_arg("throttle", None)
    def move(self, newtitle, reason=None, movetalkpage=True, sysop=False,
             deleteAndMove=False, safe=True):
        """
        Move this page to a new title.

        @param newtitle: The new page title.
        @param reason: The edit summary for the move.
        @param movetalkpage: If true, move this page's talk page (if it exists)
        @param sysop: Try to move using sysop account, if available
        @param deleteAndMove: if move succeeds, delete the old page
            (usually requires sysop privileges, depending on wiki settings)
        @param safe: If false, attempt to delete existing page at newtitle
            (if there is one) and then move this page to that title
        """
        if reason is None:
            pywikibot.output(u'Moving %s to [[%s]].'
                             % (self.title(asLink=True), newtitle))
            reason = pywikibot.input(u'Please enter a reason for the move:')
        # TODO: implement "safe" parameter (Is this necessary ?)
        # TODO: implement "sysop" parameter
        return self.site.movepage(self, newtitle, reason,
                                  movetalk=movetalkpage,
                                  noredirect=deleteAndMove)

    @deprecate_arg("throttle", None)
    def delete(self, reason=None, prompt=True, mark=False, quit=False):
        """
        Delete the page from the wiki. Requires administrator status.

        @param reason: The edit summary for the deletion, or rationale
            for deletion if requesting. If None, ask for it.
        @param prompt: If true, prompt user for confirmation before deleting.
        @param mark: If true, and user does not have sysop rights, place a
            speedy-deletion request on the page instead. If false, non-sysops
            will be asked before marking pages for deletion.
        @param quit: show also the quit option, when asking for confirmation.
        """
        if reason is None:
            pywikibot.output(u'Deleting %s.' % (self.title(asLink=True)))
            reason = pywikibot.input(u'Please enter a reason for the deletion:')

        # If user is a sysop, delete the page
        if self.site.username(sysop=True):
            answer = u'y'
            if prompt and not hasattr(self.site, '_noDeletePrompt'):
                answer = pywikibot.input_choice(
                    u'Do you want to delete %s?' % self.title(
                        asLink=True, forceInterwiki=True),
                    [('Yes', 'y'), ('No', 'n'), ('All', 'a')],
                    'n', automatic_quit=quit)
                if answer == 'a':
                    answer = 'y'
                    self.site._noDeletePrompt = True
            if answer == 'y':
                return self.site.deletepage(self, reason)
        else:  # Otherwise mark it for deletion
            if mark or hasattr(self.site, '_noMarkDeletePrompt'):
                answer = 'y'
            else:
                answer = pywikibot.input_choice(
                    u"Can't delete %s; do you want to mark it "
                    "for deletion instead?" % self.title(asLink=True,
                                                         forceInterwiki=True),
                    [('Yes', 'y'), ('No', 'n'), ('All', 'a')],
                    'n', automatic_quit=False)
                if answer == 'a':
                    answer = 'y'
                    self.site._noMarkDeletePrompt = True
            if answer == 'y':
                template = '{{delete|1=%s}}\n' % reason
                self.text = template + self.text
                return self.save(summary=reason)

    @deprecated_args(step=None)
    def loadDeletedRevisions(self, total=None):
        """
        Retrieve deleted revisions for this Page.

        Stores all revisions' timestamps, dates, editors and comments in
        self._deletedRevs attribute.

        @return: iterator of timestamps (which can be used to retrieve
            revisions later on).
        @rtype: generator
        """
        if not hasattr(self, "_deletedRevs"):
            self._deletedRevs = {}
        for item in self.site.deletedrevs(self, total=total):
            for rev in item.get("revisions", []):
                self._deletedRevs[rev['timestamp']] = rev
                yield rev['timestamp']

    def getDeletedRevision(self, timestamp, retrieveText=False):
        """
        Return a particular deleted revision by timestamp.

        @return: a list of [date, editor, comment, text, restoration
            marker]. text will be None, unless retrieveText is True (or has
            been retrieved earlier). If timestamp is not found, returns
            None.
        @rtype: list
        """
        if hasattr(self, "_deletedRevs"):
            if timestamp in self._deletedRevs and (
                    (not retrieveText) or
                    'content' in self._deletedRevs[timestamp]):
                return self._deletedRevs[timestamp]
        for item in self.site.deletedrevs(self, start=timestamp,
                                          get_text=retrieveText, total=1):
            # should only be one item with one revision
            if item['title'] == self.title:
                if "revisions" in item:
                    return item["revisions"][0]

    def markDeletedRevision(self, timestamp, undelete=True):
        """
        Mark the revision identified by timestamp for undeletion.

        @param undelete: if False, mark the revision to remain deleted.
        @type undelete: bool
        """
        if not hasattr(self, "_deletedRevs"):
            self.loadDeletedRevisions()
        if timestamp not in self._deletedRevs:
            raise ValueError(u'Timestamp %d is not a deleted revision' % timestamp)
        self._deletedRevs[timestamp]['marked'] = undelete

    @deprecated_args(comment='reason', throttle=None)
    def undelete(self, reason=None):
        """
        Undelete revisions based on the markers set by previous calls.

        If no calls have been made since loadDeletedRevisions(), everything
        will be restored.

        Simplest case::

            Page(...).undelete('This will restore all revisions')

        More complex::

            pg = Page(...)
            revs = pg.loadDeletedRevisions()
            for rev in revs:
                if ... #decide whether to undelete a revision
                    pg.markDeletedRevision(rev) #mark for undeletion
            pg.undelete('This will restore only selected revisions.')

        @param reason: Reason for the action.
        @type reason: basestring
        """
        if hasattr(self, "_deletedRevs"):
            undelete_revs = [ts for ts, rev in self._deletedRevs.items()
                             if 'marked' in rev and rev['marked']]
        else:
            undelete_revs = []
        if reason is None:
            warn('Not passing a reason for undelete() is deprecated.',
                 DeprecationWarning)
            pywikibot.output(u'Undeleting %s.' % (self.title(asLink=True)))
            reason = pywikibot.input(u'Please enter a reason for the undeletion:')
        self.site.undelete_page(self, reason, undelete_revs)

    @deprecate_arg("throttle", None)
    def protect(self, edit=False, move=False, create=None, upload=None,
                unprotect=False, reason=None, prompt=None, protections=None,
                **kwargs):
        """
        Protect or unprotect a wiki page. Requires administrator status.

        Valid protection levels (in MediaWiki 1.12) are '' (equivalent to
        'none'), 'autoconfirmed', and 'sysop'. If None is given, however,
        that protection will be skipped.

        @param protections: A dict mapping type of protection to protection
            level of that type.
        @type protections: dict
        @param reason: Reason for the action
        @type reason: basestring
        @param prompt: Whether to ask user for confirmation (deprecated).
                       Defaults to protections is None
        @type prompt: bool
        """
        def process_deprecated_arg(value, arg_name):
            # if protections was set and value is None, don't interpret that
            # argument. But otherwise warn that the parameter was set
            # (even implicit)
            if called_using_deprecated_arg:
                if value is False:  # explicit test for False (don't use not)
                    value = "sysop"
                if value == "none":  # 'none' doesn't seem do be accepted
                    value = ""
                if value is not None:  # empty string is allowed
                    protections[arg_name] = value
                    warn(u'"protections" argument of protect() replaces "{0}"'
                         .format(arg_name),
                         DeprecationWarning)
            else:
                if value:
                    warn(u'"protections" argument of protect() replaces "{0}";'
                         u' cannot use both.'.format(arg_name),
                         RuntimeWarning)

        # buffer that, because it might get changed
        called_using_deprecated_arg = protections is None
        if called_using_deprecated_arg:
            protections = {}
        process_deprecated_arg(edit, "edit")
        process_deprecated_arg(move, "move")
        process_deprecated_arg(create, "create")
        process_deprecated_arg(upload, "upload")

        if reason is None:
            pywikibot.output(u'Preparing to protection change of %s.'
                             % (self.title(asLink=True)))
            reason = pywikibot.input(u'Please enter a reason for the action:')
        if unprotect:
            warn(u'"unprotect" argument of protect() is deprecated',
                 DeprecationWarning, 2)
            protections = dict(
                (p_type, "") for p_type in self.applicable_protections())
        answer = 'y'
        if called_using_deprecated_arg and prompt is None:
            prompt = True
        if prompt:
            warn(u'"prompt" argument of protect() is deprecated',
                 DeprecationWarning, 2)
        if prompt and not hasattr(self.site, '_noProtectPrompt'):
            answer = pywikibot.input_choice(
                u'Do you want to change the protection level of %s?'
                % self.title(asLink=True, forceInterwiki=True),
                [('Yes', 'y'), ('No', 'n'), ('All', 'a')],
                'n', automatic_quit=False)
            if answer == 'a':
                answer = 'y'
                self.site._noProtectPrompt = True
        if answer == 'y':
            return self.site.protect(self, protections, reason, **kwargs)

    @deprecated_args(comment='summary')
    def change_category(self, oldCat, newCat, summary=None, sortKey=None,
                        inPlace=True, include=[]):
        """
        Remove page from oldCat and add it to newCat.

        @param oldCat: category to be removed
        @type oldCat: Category
        @param newCat: category to be added, if any
        @type newCat: Category or None

        @param summary: string to use as an edit summary

        @param sortKey: sortKey to use for the added category.
            Unused if newCat is None, or if inPlace=True
            If sortKey=True, the sortKey used for oldCat will be used.

        @param inPlace: if True, change categories in place rather than
                      rearranging them.

        @param include: list of tags not to be disabled by default in relevant
            textlib functions, where CategoryLinks can be searched.
        @type include: list

        @return: True if page was saved changed, otherwise False.
        @rtype: bool
        """
        # get list of Category objects the article is in and remove possible
        # duplicates
        cats = []
        for cat in textlib.getCategoryLinks(self.text, site=self.site,
                                            include=include):
            if cat not in cats:
                cats.append(cat)

        if not self.canBeEdited():
            pywikibot.output(u"Can't edit %s, skipping it..."
                             % self.title(asLink=True))
            return False

        if oldCat not in cats:
            pywikibot.error(u'%s is not in category %s!'
                            % (self.title(asLink=True), oldCat.title()))
            return False

        # This prevents the bot from adding newCat if it is already present.
        if newCat in cats:
            newCat = None

        oldtext = self.text
        if inPlace or self.namespace() == 10:
            newtext = textlib.replaceCategoryInPlace(oldtext, oldCat, newCat,
                                                     site=self.site)
        else:
            old_cat_pos = cats.index(oldCat)
            if newCat:
                if sortKey is True:
                    # Fetch sortKey from oldCat in current page.
                    sortKey = cats[old_cat_pos].sortKey
                cats[old_cat_pos] = Category(self.site, newCat.title(),
                                             sortKey=sortKey)
            else:
                cats.pop(old_cat_pos)

            try:
                newtext = textlib.replaceCategoryLinks(oldtext, cats)
            except ValueError:
                # Make sure that the only way replaceCategoryLinks() can return
                # a ValueError is in the case of interwiki links to self.
                pywikibot.output(u'Skipping %s because of interwiki link to '
                                 u'self' % self.title())
                return False

        if oldtext != newtext:
            try:
                self.put(newtext, summary)
                return True
            except pywikibot.PageSaveRelatedError as error:
                pywikibot.output(u'Page %s not saved: %s'
                                 % (self.title(asLink=True),
                                    error))
            except pywikibot.NoUsername:
                pywikibot.output(u'Page %s not saved; sysop privileges '
                                 u'required.' % self.title(asLink=True))
        return False

    @deprecated('Page.is_flow_page()')
    def isFlowPage(self):
        """DEPRECATED: use self.is_flow_page instead."""
        return self.is_flow_page()

    def is_flow_page(self):
        """
        Whether a page is a Flow page.

        @rtype: bool
        """
        return self.content_model == 'flow-board'

# ####### DEPRECATED METHODS ########

    @deprecated("Site.encoding()")
    def encoding(self):
        """DEPRECATED: use self.site.encoding instead."""
        return self.site.encoding()

    @deprecated("Page.title(withNamespace=False)")
    def titleWithoutNamespace(self, underscore=False):
        """DEPRECATED: use self.title(withNamespace=False) instead."""
        return self.title(underscore=underscore, withNamespace=False,
                          withSection=False)

    @deprecated("Page.title(as_filename=True)")
    def titleForFilename(self):
        """DEPRECATED: use self.title(as_filename=True) instead."""
        return self.title(as_filename=True)

    @deprecated("Page.title(withSection=False)")
    def sectionFreeTitle(self, underscore=False):
        """DEPRECATED: use self.title(withSection=False) instead."""
        return self.title(underscore=underscore, withSection=False)

    @deprecated("Page.title(asLink=True)")
    def aslink(self, forceInterwiki=False, textlink=False, noInterwiki=False):
        """DEPRECATED: use self.title(asLink=True) instead."""
        return self.title(asLink=True, forceInterwiki=forceInterwiki,
                          allowInterwiki=not noInterwiki, textlink=textlink)

    @deprecated("Page.title(asUrl=True)")
    def urlname(self):
        """Return the Page title encoded for use in an URL.

        DEPRECATED: use self.title(asUrl=True) instead.
        """
        return self.title(asUrl=True)

    @deprecated('Page.protection()')
    def getRestrictions(self):
        """DEPRECATED. Use self.protection() instead."""
        restrictions = self.protection()
        return dict((k, list(restrictions[k])) for k in restrictions)

# ###### DISABLED METHODS (warnings provided) ######
    # these methods are easily replaced by editing the page's text using
    # textlib methods and then using put() on the result.

    def removeImage(self, image, put=False, summary=None, safe=True):
        """Old method to remove all instances of an image from page."""
        warn('Page.removeImage() is no longer supported.',
             _NotImplementedWarning, 2)

    def replaceImage(self, image, replacement=None, put=False, summary=None,
                     safe=True):
        """Old method to replace all instances of an image with another."""
        warn('Page.replaceImage() is no longer supported.',
             _NotImplementedWarning, 2)


class Page(BasePage):

    """Page: A MediaWiki page."""

    @deprecated_args(defaultNamespace='ns', insite=None)
    def __init__(self, source, title=u"", ns=0):
        """Instantiate a Page object."""
        if isinstance(source, pywikibot.site.BaseSite):
            if not title:
                raise ValueError(u'Title must be specified and not empty '
                                 'if source is a Site.')
        super(Page, self).__init__(source, title, ns)

    @property
    def raw_extracted_templates(self):
        """
        Extract templates using L{textlib.extract_templates_and_params}.

        Disabled parts and whitespace are stripped, except for
        whitespace in anonymous positional arguments.

        This value is cached.

        @rtype: list of (str, OrderedDict)
        """
        if not hasattr(self, '_raw_extracted_templates'):
            templates = textlib.extract_templates_and_params(
                self.text, True, True)
            self._raw_extracted_templates = templates

        return self._raw_extracted_templates

    @deprecate_arg("get_redirect", None)
    def templatesWithParams(self):
        """
        Return templates used on this Page.

        The templates are extracted by L{textlib.extract_templates_and_params},
        with positional arguments placed first in order, and each named
        argument appearing as 'name=value'.

        All parameter keys and values for each template are stripped of
        whitespace.

        @return: a list of tuples with one tuple for each template invocation
            in the page, with the template Page as the first entry and a list of
            parameters as the second entry.
        @rtype: list of (Page, list)
        """
        # WARNING: may not return all templates used in particularly
        # intricate cases such as template substitution
        titles = [t.title() for t in self.templates()]
        templates = self.raw_extracted_templates
        # backwards-compatibility: convert the dict returned as the second
        # element into a list in the format used by old scripts
        result = []
        for template in templates:
            try:
                link = pywikibot.Link(template[0], self.site,
                                      defaultNamespace=10)
                if link.canonical_title() not in titles:
                    continue
            except pywikibot.Error:
                # this is a parser function or magic word, not template name
                # the template name might also contain invalid parts
                continue
            args = template[1]
            intkeys = {}
            named = {}
            positional = []
            for key in sorted(args):
                try:
                    intkeys[int(key)] = args[key]
                except ValueError:
                    named[key] = args[key]
            for i in range(1, len(intkeys) + 1):
                # only those args with consecutive integer keys can be
                # treated as positional; an integer could also be used
                # (out of order) as the key for a named argument
                # example: {{tmp|one|two|5=five|three}}
                if i in intkeys:
                    positional.append(intkeys[i])
                else:
                    for k in intkeys:
                        if k < 1 or k >= i:
                            named[str(k)] = intkeys[k]
                    break
            for name in named:
                positional.append("%s=%s" % (name, named[name]))
            result.append((pywikibot.Page(link, self.site), positional))
        return result

    def set_redirect_target(self, target_page, create=False, force=False,
                            keep_section=False, save=True, **kwargs):
        """
        Change the page's text to point to the redirect page.

        @param target_page: target of the redirect, this argument is required.
        @type target_page: pywikibot.Page or string
        @param create: if true, it creates the redirect even if the page
            doesn't exist.
        @type create: bool
        @param force: if true, it set the redirect target even the page
            doesn't exist or it's not redirect.
        @type force: bool
        @param keep_section: if the old redirect links to a section
            and the new one doesn't it uses the old redirect's section.
        @type keep_section: bool
        @param save: if true, it saves the page immediately.
        @type save: bool
        @param kwargs: Arguments which are used for saving the page directly
            afterwards, like 'summary' for edit summary.
        """
        if isinstance(target_page, basestring):
            target_page = pywikibot.Page(self.site, target_page)
        elif self.site != target_page.site:
            raise pywikibot.InterwikiRedirectPage(self, target_page)
        if not self.exists() and not (create or force):
            raise pywikibot.NoPage(self)
        if self.exists() and not self.isRedirectPage() and not force:
            raise pywikibot.IsNotRedirectPage(self)
        redirect_regex = self.site.redirectRegex()
        if self.exists():
            old_text = self.get(get_redirect=True)
        else:
            old_text = u''
        result = redirect_regex.search(old_text)
        if result:
            oldlink = result.group(1)
            if keep_section and '#' in oldlink and target_page.section() is None:
                sectionlink = oldlink[oldlink.index('#'):]
                target_page = pywikibot.Page(
                    self.site,
                    target_page.title() + sectionlink
                )
            prefix = self.text[:result.start()]
            suffix = self.text[result.end():]
        else:
            prefix = ''
            suffix = ''

        target_link = target_page.title(asLink=True, textlink=True,
                                        allowInterwiki=False)
        target_link = u'#{0} {1}'.format(self.site.redirect(), target_link)
        self.text = prefix + target_link + suffix
        if save:
            self.save(**kwargs)


class FilePage(Page):

    """
    A subclass of Page representing a file description page.

    Supports the same interface as Page, with some added methods.
    """

    @deprecate_arg("insite", None)
    def __init__(self, source, title=u""):
        """Constructor."""
        self._file_revisions = {}  # dictionary to cache File history.
        super(FilePage, self).__init__(source, title, 6)
        if self.namespace() != 6:
            raise ValueError(u"'%s' is not in the file namespace!" % title)

    def _load_file_revisions(self, imageinfo):
        for file_rev in imageinfo:
            file_revision = FileInfo(file_rev)
            self._file_revisions[file_revision.timestamp] = file_revision

    @property
    def latest_file_info(self):
        """
        Retrieve and store information of latest Image rev. of FilePage.

        At the same time, the whole history of Image is fetched and cached in
        self._file_revisions

        @return: instance of FileInfo()
        """
        if not len(self._file_revisions):
            self.site.loadimageinfo(self, history=True)
        latest_ts = max(self._file_revisions)
        return self._file_revisions[latest_ts]

    @property
    def oldest_file_info(self):
        """
        Retrieve and store information of oldest Image rev. of FilePage.

        At the same time, the whole history of Image is fetched and cached in
        self._file_revisions

        @return: instance of FileInfo()
        """
        if not len(self._file_revisions):
            self.site.loadimageinfo(self, history=True)
        oldest_ts = min(self._file_revisions)
        return self._file_revisions[oldest_ts]

    def get_file_history(self):
        """
        Return the file's version history.

        @return: dictionary with:
            key: timestamp of the entry
            value: instance of FileInfo()
        @rtype: dict
        """
        if not len(self._file_revisions):
            self.site.loadimageinfo(self, history=True)
        return self._file_revisions

    def getImagePageHtml(self):
        """
        Download the file page, and return the HTML, as a unicode string.

        Caches the HTML code, so that if you run this method twice on the
        same FilePage object, the page will only be downloaded once.
        """
        if not hasattr(self, '_imagePageHtml'):
            path = "%s/index.php?title=%s" \
                   % (self.site.scriptpath(), self.title(asUrl=True))
            self._imagePageHtml = http.request(self.site, path)
        return self._imagePageHtml

    @deprecated('get_file_url')
    def fileUrl(self):
        """Return the URL for the file described on this page."""
        return self.latest_file_info.url

    def get_file_url(self, url_width=None, url_height=None, url_param=None):
        """
        Return the url or the thumburl of the file described on this page.

        Fetch the information if not available.

        Once retrieved, thumburl information will also be accessible as
        latest_file_info attributes, named as in [1]:
        - url, thumburl, thumbwidth and thumbheight

        Parameters correspond to iiprops in:
        [1] U{https://www.mediawiki.org/wiki/API:Imageinfo}

        Parameters validation and error handling left to the API call.

        @param width: see iiurlwidth in [1]
        @param height: see iiurlheigth in [1]
        @param param: see iiurlparam in [1]

        @return: latest file url or thumburl
        @rtype: unicode

        """
        # Plain url is requested.
        if url_width is None and url_height is None and url_param is None:
            return self.latest_file_info.url

        # Thumburl is requested.
        self.site.loadimageinfo(self, history=not self._file_revisions,
                                url_width=url_width, url_height=url_height,
                                url_param=url_param)
        return self.latest_file_info.thumburl

    @deprecated("fileIsShared")
    def fileIsOnCommons(self):
        """
        DEPRECATED. Check if the image is stored on Wikimedia Commons.

        @rtype: bool
        """
        return self.fileIsShared()

    def fileIsShared(self):
        """
        Check if the file is stored on any known shared repository.

        @rtype: bool
        """
        # as of now, the only known repositories are commons and wikitravel
        # TODO: put the URLs to family file
        if not self.site.has_image_repository:
            return False
        elif 'wikitravel_shared' in self.site.shared_image_repository():
            return self.latest_file_info.url.startswith(
                u'http://wikitravel.org/upload/shared/')
        else:
            return self.latest_file_info.url.startswith(
                'https://upload.wikimedia.org/wikipedia/commons/')

    @deprecated("FilePage.latest_file_info.sha1")
    def getFileMd5Sum(self):
        """Return image file's MD5 checksum."""
        # TODO: check whether this needs a User-Agent header added
        req = http.fetch(self.fileUrl())
        h = hashlib.md5()
        h.update(req.raw)
        md5Checksum = h.hexdigest()
        return md5Checksum

    @deprecated("FilePage.latest_file_info.sha1")
    def getFileSHA1Sum(self):
        """Return the file's SHA1 checksum."""
        return self.latest_file_info.sha1

    @deprecated("FilePage.oldest_file_info.user")
    def getFirstUploader(self):
        """
        Return a list with first uploader of the FilePage and timestamp.

        For compatibility with compat only.
        """
        return [self.oldest_file_info.user,
                unicode(self.oldest_file_info.timestamp.isoformat())]

    @deprecated("FilePage.latest_file_info.user")
    def getLatestUploader(self):
        """
        Return a list with latest uploader of the FilePage and timestamp.

        For compatibility with compat only.
        """
        return [self.latest_file_info.user,
                unicode(self.latest_file_info.timestamp.isoformat())]

    @deprecated('FilePage.get_file_history()')
    def getFileVersionHistory(self):
        """
        Return the file's version history.

        @return: A list of dictionaries with the following keys:

            [comment, sha1, url, timestamp, metadata,
             height, width, mime, user, descriptionurl, size]
        @rtype: list
        """
        return self.site.loadimageinfo(self, history=True)

    def getFileVersionHistoryTable(self):
        """Return the version history in the form of a wiki table."""
        lines = []
        for info in self.getFileVersionHistory():
            dimension = '{width}×{height} px ({size} bytes)'.format(**info)
            lines.append('| {timestamp} || {user} || {dimension} |'
                         '| <nowiki>{comment}</nowiki>'
                         ''.format(dimension=dimension, **info))
        return ('{| class="wikitable"\n'
                '! {{int:filehist-datetime}} || {{int:filehist-user}} |'
                '| {{int:filehist-dimensions}} || {{int:filehist-comment}}\n'
                '|-\n%s\n|}\n' % '\n|-\n'.join(lines))

    @deprecated_args(step=None)
    def usingPages(self, total=None, content=False):
        """
        Yield Pages on which the file is displayed.

        @param total: iterate no more than this number of pages in total
        @param content: if True, load the current content of each iterated page
            (default False)
        """
        return self.site.imageusage(self, total=total, content=content)

    def upload(self, source, **kwargs):
        """
        Upload this file to the wiki.

        keyword arguments are from site.upload() method.

        @param source: Path or URL to the file to be uploaded.
        @type source: str

        @keyword comment: Edit summary; if this is not provided, then
            filepage.text will be used. An empty summary is not permitted.
            This may also serve as the initial page text (see below).
        @keyword text: Initial page text; if this is not set, then
            filepage.text will be used, or comment.
        @keyword watch: If true, add filepage to the bot user's watchlist
        @keyword ignore_warnings: It may be a static boolean, a callable returning
            a boolean or an iterable. The callable gets a list of UploadWarning
            instances and the iterable should contain the warning codes for
            which an equivalent callable would return True if all UploadWarning
            codes are in thet list. If the result is False it'll not continue
            uploading the file and otherwise disable any warning and
            reattempt to upload the file. NOTE: If report_success is True or
            None it'll raise an UploadWarning exception if the static boolean is
            False.
        @type ignore_warnings: bool or callable or iterable of str
        @keyword chunk_size: The chunk size in bytesfor chunked uploading (see
            U{https://www.mediawiki.org/wiki/API:Upload#Chunked_uploading}). It
            will only upload in chunks, if the version number is 1.20 or higher
            and the chunk size is positive but lower than the file size.
        @type chunk_size: int
        @keyword _file_key: Reuses an already uploaded file using the filekey. If
            None (default) it will upload the file.
        @type _file_key: str or None
        @keyword _offset: When file_key is not None this can be an integer to
            continue a previously canceled chunked upload. If False it treats
            that as a finished upload. If True it requests the stash info from
            the server to determine the offset. By default starts at 0.
        @type _offset: int or bool
        @keyword _verify_stash: Requests the SHA1 and file size uploaded and
            compares it to the local file. Also verifies that _offset is
            matching the file size if the _offset is an int. If _offset is False
            if verifies that the file size match with the local file. If None
            it'll verifies the stash when a file key and offset is given.
        @type _verify_stash: bool or None
        @keyword report_success: If the upload was successful it'll print a
            success message and if ignore_warnings is set to False it'll
            raise an UploadWarning if a warning occurred. If it's None (default)
            it'll be True if ignore_warnings is a bool and False otherwise. If
            it's True or None ignore_warnings must be a bool.
        @return: It returns True if the upload was successful and False
            otherwise.
        @rtype: bool
        """
        filename = url = None
        if '://' in source:
            url = source
        else:
            filename = source
        return self.site.upload(self, source_filename=filename, source_url=url,
                                **kwargs)

    def download(self, filename=None, chunk_size=100 * 1024):
        """
        Download to filename file of FilePage.

        @param filename: filename where to save file:
            None: self.title(as_filename=True, withNamespace=False)
            will be used
            str: provided filename will be used.
        @type None or str
        @return: True if download is successful, False otherwise.
        @raise: IOError if filename cannot be written for any reason.
        """
        if filename is None:
            filename = self.title(as_filename=True, withNamespace=False)

        filename = os.path.expanduser(filename)

        req = http.fetch(self.latest_file_info.url, stream=True)
        if req.status == 200:
            try:
                with open(filename, 'wb') as f:
                    for chunk in req.data.iter_content(chunk_size):
                        f.write(chunk)
            except IOError as e:
                raise e

            sha1 = compute_file_hash(filename)
            return sha1 == self.latest_file_info.sha1
        else:
            pywikibot.warning('Unsuccesfull request (%s): %s' % (req.status, req.uri))
            return False


wrapper = _ModuleDeprecationWrapper(__name__)
wrapper._add_deprecated_attr('ImagePage', FilePage)


class Category(Page):

    """A page in the Category: namespace."""

    @deprecate_arg("insite", None)
    def __init__(self, source, title=u"", sortKey=None):
        """
        Constructor.

        All parameters are the same as for Page() constructor.
        """
        self.sortKey = sortKey
        Page.__init__(self, source, title, ns=14)
        if self.namespace() != 14:
            raise ValueError(u"'%s' is not in the category namespace!"
                             % title)

    @deprecated_args(forceInterwiki=None, textlink=None, noInterwiki=None)
    def aslink(self, sortKey=None):
        """
        Return a link to place a page in this Category.

        Use this only to generate a "true" category link, not for interwikis
        or text links to category pages.

        @param sortKey: The sort key for the article to be placed in this
            Category; if omitted, default sort key is used.
        @type sortKey: (optional) unicode
        """
        key = sortKey or self.sortKey
        if key is not None:
            titleWithSortKey = '%s|%s' % (self.title(withSection=False),
                                          key)
        else:
            titleWithSortKey = self.title(withSection=False)
        return '[[%s]]' % titleWithSortKey

    @deprecated_args(startFrom=None, cacheResults=None, step=None)
    def subcategories(self, recurse=False, total=None, content=False):
        """
        Iterate all subcategories of the current category.

        @param recurse: if not False or 0, also iterate subcategories of
            subcategories. If an int, limit recursion to this number of
            levels. (Example: recurse=1 will iterate direct subcats and
            first-level sub-sub-cats, but no deeper.)
        @type recurse: int or bool
        @param total: iterate no more than this number of
            subcategories in total (at all levels)
        @param content: if True, retrieve the content of the current version
            of each category description page (default False)
        """
        if not isinstance(recurse, bool) and recurse:
            recurse = recurse - 1
        if not hasattr(self, "_subcats"):
            self._subcats = []
            for member in self.site.categorymembers(
                    self, member_type='subcat', total=total, content=content):
                subcat = Category(member)
                self._subcats.append(subcat)
                yield subcat
                if total is not None:
                    total -= 1
                    if total == 0:
                        return
                if recurse:
                    for item in subcat.subcategories(
                            recurse, total=total, content=content):
                        yield item
                        if total is not None:
                            total -= 1
                            if total == 0:
                                return
        else:
            for subcat in self._subcats:
                yield subcat
                if total is not None:
                    total -= 1
                    if total == 0:
                        return
                if recurse:
                    for item in subcat.subcategories(
                            recurse, total=total, content=content):
                        yield item
                        if total is not None:
                            total -= 1
                            if total == 0:
                                return

    @deprecated_args(startFrom='startsort', step=None)
    def articles(self, recurse=False, total=None,
                 content=False, namespaces=None, sortby=None,
                 reverse=False, starttime=None, endtime=None,
                 startsort=None, endsort=None):
        """
        Yield all articles in the current category.

        By default, yields all *pages* in the category that are not
        subcategories!

        @param recurse: if not False or 0, also iterate articles in
            subcategories. If an int, limit recursion to this number of
            levels. (Example: recurse=1 will iterate articles in first-level
            subcats, but no deeper.)
        @type recurse: int or bool
        @param total: iterate no more than this number of pages in
            total (at all levels)
        @param namespaces: only yield pages in the specified namespaces
        @type namespaces: int or list of ints
        @param content: if True, retrieve the content of the current version
            of each page (default False)
        @param sortby: determines the order in which results are generated,
            valid values are "sortkey" (default, results ordered by category
            sort key) or "timestamp" (results ordered by time page was
            added to the category). This applies recursively.
        @type sortby: str
        @param reverse: if True, generate results in reverse order
            (default False)
        @param starttime: if provided, only generate pages added after this
            time; not valid unless sortby="timestamp"
        @type starttime: pywikibot.Timestamp
        @param endtime: if provided, only generate pages added before this
            time; not valid unless sortby="timestamp"
        @type endtime: pywikibot.Timestamp
        @param startsort: if provided, only generate pages >= this title
            lexically; not valid if sortby="timestamp"
        @type startsort: str
        @param endsort: if provided, only generate pages <= this title
            lexically; not valid if sortby="timestamp"
        @type endsort: str
        """
        for member in self.site.categorymembers(self,
                                                namespaces=namespaces,
                                                total=total,
                                                content=content, sortby=sortby,
                                                reverse=reverse,
                                                starttime=starttime,
                                                endtime=endtime,
                                                startsort=startsort,
                                                endsort=endsort,
                                                member_type=['page', 'file']
                                                ):
            yield member
            if total is not None:
                total -= 1
                if total == 0:
                    return
        if recurse:
            if not isinstance(recurse, bool) and recurse:
                recurse = recurse - 1
            for subcat in self.subcategories():
                for article in subcat.articles(recurse, total=total,
                                               content=content,
                                               namespaces=namespaces,
                                               sortby=sortby,
                                               reverse=reverse,
                                               starttime=starttime,
                                               endtime=endtime,
                                               startsort=startsort,
                                               endsort=endsort
                                               ):
                    yield article
                    if total is not None:
                        total -= 1
                        if total == 0:
                            return

    @deprecated_args(step=None)
    def members(self, recurse=False, namespaces=None, total=None,
                content=False):
        """Yield all category contents (subcats, pages, and files)."""
        for member in self.site.categorymembers(
                self, namespaces, total=total, content=content):
            yield member
            if total is not None:
                total -= 1
                if total == 0:
                    return
        if recurse:
            if not isinstance(recurse, bool) and recurse:
                recurse = recurse - 1
            for subcat in self.subcategories():
                for article in subcat.members(
                        recurse, namespaces, total=total, content=content):
                    yield article
                    if total is not None:
                        total -= 1
                        if total == 0:
                            return

    @need_version('1.13')
    def isEmptyCategory(self):
        """
        Return True if category has no members (including subcategories).

        @rtype: bool
        """
        ci = self.categoryinfo
        return sum(ci[k] for k in ['files', 'pages', 'subcats']) == 0

    @need_version('1.11')
    def isHiddenCategory(self):
        """
        Return True if the category is hidden.

        @rtype: bool
        """
        return u'hiddencat' in self.properties()

    def copyTo(self, cat, message):
        """
        Copy text of category page to a new page. Does not move contents.

        @param cat: New category title (without namespace) or Category object
        @type cat: unicode or Category
        @param message: message to use for category creation message
            If two %s are provided in message, will be replaced
            by (self.title, authorsList)
        @type message: unicode
        @return: True if copying was successful, False if target page
            already existed.
        @rtype: bool
        """
        # This seems far too specialized to be in the top-level framework
        # move to category.py? (Although it doesn't seem to be used there,
        # either)
        if not isinstance(cat, Category):
            cat = self.site.namespaces.CATEGORY + ':' + cat
            targetCat = Category(self.site, cat)
        else:
            targetCat = cat
        if targetCat.exists():
            pywikibot.output(u'Target page %s already exists!'
                             % targetCat.title(),
                             level=pywikibot.logging.WARNING)
            return False
        else:
            pywikibot.output('Moving text from %s to %s.'
                             % (self.title(), targetCat.title()))
            authors = ', '.join(self.contributingUsers())
            try:
                creationSummary = message % (self.title(), authors)
            except TypeError:
                creationSummary = message
            targetCat.put(self.get(), creationSummary)
            return True

    def copyAndKeep(self, catname, cfdTemplates, message):
        """
        Copy partial category page text (not contents) to a new title.

        Like copyTo above, except this removes a list of templates (like
        deletion templates) that appear in the old category text. It also
        removes all text between the two HTML comments BEGIN CFD TEMPLATE
        and END CFD TEMPLATE. (This is to deal with CFD templates that are
        substituted.)

        Returns true if copying was successful, false if target page already
        existed.

        @param catname: New category title (without namespace)
        @param cfdTemplates: A list (or iterator) of templates to be removed
            from the page text
        @return: True if copying was successful, False if target page
            already existed.
        @rtype: bool
        """
        # I don't see why we need this as part of the framework either
        # move to scripts/category.py?
        catname = self.site.namespaces.CATEGORY + ':' + catname
        targetCat = Category(self.site, catname)
        if targetCat.exists():
            pywikibot.warning(u'Target page %s already exists!'
                              % targetCat.title())
            return False
        else:
            pywikibot.output(
                'Moving text from %s to %s.'
                % (self.title(), targetCat.title()))
            authors = ', '.join(self.contributingUsers())
            creationSummary = message % (self.title(), authors)
            newtext = self.get()
        for regexName in cfdTemplates:
            matchcfd = re.compile(r"{{%s.*?}}" % regexName, re.IGNORECASE)
            newtext = matchcfd.sub('', newtext)
            matchcomment = re.compile(
                r"<!--BEGIN CFD TEMPLATE-->.*?<!--END CFD TEMPLATE-->",
                re.IGNORECASE | re.MULTILINE | re.DOTALL)
            newtext = matchcomment.sub('', newtext)
            pos = 0
            while (newtext[pos:pos + 1] == "\n"):
                pos = pos + 1
            newtext = newtext[pos:]
            targetCat.put(newtext, creationSummary)
            return True

    @property
    def categoryinfo(self):
        """
        Return a dict containing information about the category.

        The dict contains values for:

        Numbers of pages, subcategories, files, and total contents.

        @rtype: dict
        """
        return self.site.categoryinfo(self)

    def newest_pages(self, total=None):
        """
        Return pages in a category ordered by the creation date.

        If two or more pages are created at the same time, the pages are
        returned in the order they were added to the category. The most recently
        added page is returned first.

        It only allows to return the pages ordered from newest to oldest, as it
        is impossible to determine the oldest page in a category without
        checking all pages. But it is possible to check the category in order
        with the newly added first and it yields all pages which were created
        after the currently checked page was added (and thus there is no page
        created after any of the cached but added before the currently checked).

        @param total: The total number of pages queried.
        @type total: int
        @return: A page generator of all pages in a category ordered by the
            creation date. From newest to oldest. Note: It currently only
            returns Page instances and not a subclass of it if possible. This
            might change so don't expect to only get Page instances.
        @rtype: generator
        """
        def check_cache(latest):
            """Return the cached pages in order and not more than total."""
            cached = []
            for timestamp in sorted((ts for ts in cache if ts > latest),
                                    reverse=True):
                # The complete list can be removed, it'll either yield all of
                # them, or only a portion but will skip the rest anyway
                cached += cache.pop(timestamp)[:None if total is None else
                                               total - len(cached)]
                if total and len(cached) >= total:
                    break  # already got enough
            assert total is None or len(cached) <= total, \
                'Number of caches is more than total number requested'
            return cached

        # all pages which have been checked but where created before the
        # current page was added, at some point they will be created after
        # the current page was added. It saves all pages via the creation
        # timestamp. Be prepared for multiple pages.
        cache = defaultdict(list)
        # TODO: Make site.categorymembers is usable as it returns pages
        # There is no total defined, as it's not known how many pages need to be
        # checked before the total amount of new pages was found. In worst case
        # all pages of a category need to be checked.
        for member in pywikibot.data.api.QueryGenerator(
                site=self.site, list='categorymembers', cmsort='timestamp',
                cmdir='older', cmprop='timestamp|title',
                cmtitle=self.title()):
            # TODO: Upcast to suitable class
            page = pywikibot.Page(self.site, member['title'])
            assert page.namespace() == member['ns'], \
                'Namespace of the page is not consistent'
            cached = check_cache(pywikibot.Timestamp.fromISOformat(
                member['timestamp']))
            for cached_page in cached:
                yield cached_page
            if total is not None:
                total -= len(cached)
                if total <= 0:
                    break
            cache[page.oldest_revision.timestamp] += [page]
        else:
            # clear cache
            assert total is None or total > 0, \
                'As many items as given in total already returned'
            for cached_page in check_cache(pywikibot.Timestamp.min):
                yield cached_page

# ### DEPRECATED METHODS ####
    @deprecated("list(Category.subcategories(...))")
    def subcategoriesList(self, recurse=False):
        """DEPRECATED: Equivalent to list(self.subcategories(...))."""
        return sorted(list(set(self.subcategories(recurse))))

    @deprecated("list(Category.articles(...))")
    def articlesList(self, recurse=False):
        """DEPRECATED: equivalent to list(self.articles(...))."""
        return sorted(list(set(self.articles(recurse))))

    @deprecated("Category.categories()")
    def supercategories(self):
        """DEPRECATED: equivalent to self.categories()."""
        return self.categories()

    @deprecated("list(Category.categories(...))")
    def supercategoriesList(self):
        """DEPRECATED: equivalent to list(self.categories(...))."""
        return sorted(list(set(self.categories())))


class User(Page):

    """
    A class that represents a Wiki user.

    This class also represents the Wiki page User:<username>
    """

    @deprecated_args(site="source", name="title")
    def __init__(self, source, title=u''):
        """
        Initializer for a User object.

        All parameters are the same as for Page() constructor.
        """
        if len(title) > 1 and title[0] == u'#':
            self._isAutoblock = True
            title = title[1:]
        else:
            self._isAutoblock = False
        Page.__init__(self, source, title, ns=2)
        if self.namespace() != 2:
            raise ValueError(u"'%s' is not in the user namespace!"
                             % title)
        if self._isAutoblock:
            # This user is probably being queried for purpose of lifting
            # an autoblock.
            pywikibot.output(
                "This is an autoblock ID, you can only use to unblock it.")

    @deprecated('User.username')
    def name(self):
        """
        The username.

        DEPRECATED: use username instead.

        @rtype: unicode
        """
        return self.username

    @property
    def username(self):
        """
        The username.

        Convenience method that returns the title of the page with
        namespace prefix omitted, which is the username.

        @rtype: unicode
        """
        if self._isAutoblock:
            return u'#' + self.title(withNamespace=False)
        else:
            return self.title(withNamespace=False)

    def isRegistered(self, force=False):
        """
        Determine if the user is registered on the site.

        It is possible to have a page named User:xyz and not have
        a corresponding user with username xyz.

        The page does not need to exist for this method to return
        True.

        @param force: if True, forces reloading the data from API
        @type force: bool

        @rtype: bool
        """
        # T135828: the registration timestamp may be None but the key exists
        return 'registration' in self.getprops(force)

    def isAnonymous(self):
        """
        Determine if the user is editing as an IP address.

        @rtype: bool
        """
        return is_IP(self.username)

    def getprops(self, force=False):
        """
        Return a properties about the user.

        @param force: if True, forces reloading the data from API
        @type force: bool

        @rtype: dict
        """
        if force and hasattr(self, '_userprops'):
            del self._userprops
        if not hasattr(self, '_userprops'):
            self._userprops = list(self.site.users([self.username, ]))[0]
            if self.isAnonymous():
                r = list(self.site.blocks(users=self.username))
                if r:
                    self._userprops['blockedby'] = r[0]['by']
                    self._userprops['blockreason'] = r[0]['reason']
        return self._userprops

    @deprecated('User.registration()')
    def registrationTime(self, force=False):
        """
        DEPRECATED. Fetch registration date for this user.

        @param force: if True, forces reloading the data from API
        @type force: bool

        @return: long (MediaWiki's internal timestamp format) or 0
        @rtype: int or long
        """
        if self.registration():
            return long(self.registration().strftime('%Y%m%d%H%M%S'))
        else:
            return 0

    def registration(self, force=False):
        """
        Fetch registration date for this user.

        @param force: if True, forces reloading the data from API
        @type force: bool

        @rtype: pywikibot.Timestamp or None
        """
        reg = self.getprops(force).get('registration')
        if reg:
            return pywikibot.Timestamp.fromISOformat(reg)

    def editCount(self, force=False):
        """
        Return edit count for a registered user.

        Always returns 0 for 'anonymous' users.

        @param force: if True, forces reloading the data from API
        @type force: bool

        @rtype: int or long
        """
        return self.getprops(force).get('editcount', 0)

    def isBlocked(self, force=False):
        """
        Determine whether the user is currently blocked.

        @param force: if True, forces reloading the data from API
        @type force: bool

        @rtype: bool
        """
        return 'blockedby' in self.getprops(force)

    def isEmailable(self, force=False):
        """
        Determine whether emails may be send to this user through MediaWiki.

        @param force: if True, forces reloading the data from API
        @type force: bool

        @rtype: bool
        """
        return 'emailable' in self.getprops(force)

    def groups(self, force=False):
        """
        Return a list of groups to which this user belongs.

        The list of groups may be empty.

        @param force: if True, forces reloading the data from API
        @type force: bool
        @return: groups property
        @rtype: list
        """
        return self.getprops(force).get('groups', [])

    def getUserPage(self, subpage=u''):
        """
        Return a Page object relative to this user's main page.

        @param subpage: subpage part to be appended to the main
                            page title (optional)
        @type subpage: unicode
        @return: Page object of user page or user subpage
        @rtype: Page
        """
        if self._isAutoblock:
            # This user is probably being queried for purpose of lifting
            # an autoblock, so has no user pages per se.
            raise AutoblockUser(
                "This is an autoblock ID, you can only use to unblock it.")
        if subpage:
            subpage = u'/' + subpage
        return Page(Link(self.title() + subpage, self.site))

    def getUserTalkPage(self, subpage=u''):
        """
        Return a Page object relative to this user's main talk page.

        @param subpage: subpage part to be appended to the main
                            talk page title (optional)
        @type subpage: unicode
        @return: Page object of user talk page or user talk subpage
        @rtype: Page
        """
        if self._isAutoblock:
            # This user is probably being queried for purpose of lifting
            # an autoblock, so has no user talk pages per se.
            raise AutoblockUser(
                "This is an autoblock ID, you can only use to unblock it.")
        if subpage:
            subpage = u'/' + subpage
        return Page(Link(self.username + subpage,
                         self.site, defaultNamespace=3))

    def send_email(self, subject, text, ccme=False):
        """
        Send an email to this user via MediaWiki's email interface.

        @param subject: the subject header of the mail
        @type subject: unicode
        @param text: mail body
        @type text: unicode
        @param ccme: if True, sends a copy of this email to the bot
        @type ccme: bool
        @raises NotEmailableError: the user of this User is not emailable
        @raises UserRightsError: logged in user does not have 'sendemail' right
        @return: operation successful indicator
        @rtype: bool
        """
        if not self.isEmailable():
            raise NotEmailableError(self)

        if not self.site.has_right('sendemail'):
            raise UserRightsError('You don\'t have permission to send mail')

        params = {
            'action': 'emailuser',
            'target': self.username,
            'token': self.site.tokens['email'],
            'subject': subject,
            'text': text,
        }
        if ccme:
            params['ccme'] = 1
        mailrequest = self.site._simple_request(**params)
        maildata = mailrequest.submit()

        if 'emailuser' in maildata:
            if maildata['emailuser']['result'] == u'Success':
                return True
        return False

    @deprecated('send_email')
    def sendMail(self, subject, text, ccme=False):
        """
        Send an email to this user via MediaWiki's email interface.

        Outputs 'Email sent' if the email was sent.

        @param subject: the subject header of the mail
        @type subject: unicode
        @param text: mail body
        @type text: unicode
        @param ccme: if True, sends a copy of this email to the bot
        @type ccme: bool
        @raises NotEmailableError: the user of this User is not emailable
        @raises UserRightsError: logged in user does not have 'sendemail' right
        @return: operation successful indicator
        @rtype: bool
        """
        if self.send_email(subject, text, ccme=ccme):
            pywikibot.output('Email sent.')
            return True
        return False

    def block(self, expiry, reason, anononly=True, nocreate=True,
              autoblock=True, noemail=False, reblock=False):
        """
        Block user.

        @param expiry: When the block should expire
        @type expiry: pywikibot.Timestamp|str
        @param reason: Block reason
        @type reason: basestring
        @param anononly: Whether block should only affect anonymous users
        @type anononly: bool
        @param nocreate: Whether to block account creation
        @type nocreate: bool
        @param autoblock: Whether to enable autoblock
        @type autoblock: bool
        @param noemail: Whether to disable email access
        @type noemail: bool
        @param reblock: Whether to reblock if a block already is set
        @type reblock: bool
        @return: None
        """
        try:
            self.site.blockuser(self, expiry, reason, anononly, nocreate,
                                autoblock, noemail, reblock)
        except APIError as err:
            if err.code == 'invalidrange':
                raise ValueError("%s is not a valid IP range." % self.username)
            else:
                raise err

    def unblock(self, reason=None):
        """
        Remove the block for the user.

        @param reason: Reason for the unblock.
        @type reason: basestring
        """
        self.site.unblockuser(self, reason)

    @deprecated("contributions")
    @deprecate_arg("limit", "total")  # To be consistent with rest of framework
    def editedPages(self, total=500):
        """
        DEPRECATED. Use contributions().

        Yields pywikibot.Page objects that this user has
        edited, with an upper bound of 'total'. Pages returned are not
        guaranteed to be unique.

        @param total: limit result to this number of pages.
        @type total: int.
        """
        for item in self.contributions(total=total):
            yield item[0]

    @deprecated_args(limit='total', namespace='namespaces')
    def contributions(self, total=500, namespaces=[]):
        """
        Yield tuples describing this user edits.

        Each tuple is composed of a pywikibot.Page object,
        the revision id (int), the edit timestamp (as a pywikibot.Timestamp
        object), and the comment (unicode).
        Pages returned are not guaranteed to be unique.

        @param total: limit result to this number of pages
        @type total: int
        @param namespaces: only iterate links in these namespaces
        @type namespaces: list
        """
        for contrib in self.site.usercontribs(
                user=self.username, namespaces=namespaces, total=total):
            ts = pywikibot.Timestamp.fromISOformat(contrib['timestamp'])
            yield (Page(self.site, contrib['title'], contrib['ns']),
                   contrib['revid'],
                   ts,
                   contrib.get('comment'))

    @deprecate_arg("number", "total")
    def uploadedImages(self, total=10):
        """
        Yield tuples describing files uploaded by this user.

        Each tuple is composed of a pywikibot.Page, the timestamp (str in
        ISO8601 format), comment (unicode) and a bool for pageid > 0.
        Pages returned are not guaranteed to be unique.

        @param total: limit result to this number of pages
        @type total: int
        """
        if not self.isRegistered():
            raise StopIteration
        for item in self.site.logevents(
                logtype='upload', user=self.username, total=total):
            yield (item.page(),
                   unicode(item.timestamp()),
                   item.comment(),
                   item.pageid() > 0
                   )


class WikibasePage(BasePage):

    """
    The base page for the Wikibase extension.

    There should be no need to instantiate this directly.
    """

    def __init__(self, site, title=u"", **kwargs):
        """
        Constructor.

        If title is provided, either ns or entity_type must also be provided,
        and will be checked against the title parsed using the Page
        initialisation logic.

        @param site: Wikibase data site
        @type site: DataSite
        @param title: normalized title of the page
        @type title: unicode
        @kwarg ns: namespace
        @type ns: Namespace instance, or int
        @kwarg entity_type: Wikibase entity type
        @type entity_type: str ('item' or 'property')

        @raises TypeError: incorrect use of parameters
        @raises ValueError: incorrect namespace
        @raises pywikibot.Error: title parsing problems
        @raises NotImplementedError: the entity type is not supported
        """
        if not isinstance(site, pywikibot.site.DataSite):
            raise TypeError("site must be a pywikibot.site.DataSite object")
        if title and ('ns' not in kwargs and 'entity_type' not in kwargs):
            pywikibot.debug("%s.__init__: %s title %r specified without "
                            "ns or entity_type"
                            % (self.__class__.__name__, site, title),
                            layer='wikibase')

        self._namespace = None

        if 'ns' in kwargs:
            if isinstance(kwargs['ns'], Namespace):
                self._namespace = kwargs.pop('ns')
                kwargs['ns'] = self._namespace.id
            else:
                # numerical namespace given
                ns = int(kwargs['ns'])
                if site.item_namespace.id == ns:
                    self._namespace = site.item_namespace
                elif site.property_namespace.id == ns:
                    self._namespace = site.property_namespace
                else:
                    raise ValueError('%r: Namespace "%d" is not valid'
                                     % self.site)

        if 'entity_type' in kwargs:
            entity_type = kwargs.pop('entity_type')
            if entity_type == 'item':
                entity_type_ns = site.item_namespace
            elif entity_type == 'property':
                entity_type_ns = site.property_namespace
            else:
                raise ValueError('Wikibase entity type "%s" unknown'
                                 % entity_type)

            if self._namespace:
                if self._namespace != entity_type_ns:
                    raise ValueError('Namespace "%d" is not valid for Wikibase'
                                     ' entity type "%s"'
                                     % (kwargs['ns'], entity_type))
            else:
                self._namespace = entity_type_ns
                kwargs['ns'] = self._namespace.id

        super(WikibasePage, self).__init__(site, title, **kwargs)

        # If a title was not provided,
        # avoid checks which may cause an exception.
        if not title:
            self.repo = site
            return

        if self._namespace:
            if self._link.namespace != self._namespace.id:
                raise ValueError(u"'%s' is not in the namespace %d"
                                 % (title, self._namespace.id))
        else:
            # Neither ns or entity_type was provided.
            # Use the _link to determine entity type.
            ns = self._link.namespace
            if self.site.item_namespace.id == ns:
                self._namespace = self.site.item_namespace
            elif self.site.property_namespace.id == ns:
                self._namespace = self.site.property_namespace
            else:
                raise ValueError('%r: Namespace "%r" is not valid'
                                 % (self.site, ns))

        # .site forces a parse of the Link title to determine site
        self.repo = self.site
        # Link.__init__, called from Page.__init__, has cleaned the title
        # stripping whitespace and uppercasing the first letter according
        # to the namespace case=first-letter.
        self.id = self._link.title
        if not self.is_valid_id(self.id):
            raise pywikibot.InvalidTitle(
                "'%s' is not a valid %s page title"
                % (self.id, self.entity_type))

    def _defined_by(self, singular=False):
        """
        Internal function to provide the API parameters to identify the entity.

        The API parameters may be 'id' if the ItemPage has one,
        or 'site'&'title' if instantiated via ItemPage.fromPage with
        lazy_load enabled.

        Once an item's "p/q##" is looked up, that will be used for all future
        requests.

        An empty dict is returned if the ItemPage is instantiated without
        either ID (internally it has id = '-1') or site&title.

        @param singular: Whether the parameter names should use the singular
                         form
        @type singular: bool
        @return: API parameters
        @rtype: dict
        """
        params = {}
        if singular:
            id = 'id'
            site = 'site'
            title = 'title'
        else:
            id = 'ids'
            site = 'sites'
            title = 'titles'

        lazy_loading_id = not hasattr(self, 'id') and hasattr(self, '_site')

        # id overrides all
        if hasattr(self, 'id'):
            if self.id != '-1':
                params[id] = self.id
        elif lazy_loading_id:
            params[site] = self._site.dbName()
            params[title] = self._title
        else:
            # if none of the above applies, this item is in an invalid state
            # which needs to be raise as an exception, but also logged in case
            # an exception handler is catching the generic Error.
            pywikibot.error('%s is in invalid state'
                            % self.__class__.__name__)
            raise pywikibot.Error('%s is in invalid state'
                                  % self.__class__.__name__)

        return params

    def __getattribute__(self, name):
        """Low-level attribute getter. Deprecates lastrevid."""
        if name == 'lastrevid':
            issue_deprecation_warning(
                'WikibasePage.lastrevid', 'latest_revision_id', 2)
            name = '_revid'
        return super(WikibasePage, self).__getattribute__(name)

    def __setattr__(self, attr, value):
        """Attribute setter. Deprecates lastrevid."""
        if attr == 'lastrevid':
            issue_deprecation_warning(
                'WikibasePage.lastrevid', 'latest_revision_id', 2)
            attr = '_revid'
        return super(WikibasePage, self).__setattr__(attr, value)

    def __delattr__(self, attr):
        """Attribute deleter. Deprecates lastrevid."""
        if attr == 'lastrevid':
            issue_deprecation_warning(
                'WikibasePage.lastrevid', 'latest_revision_id', 2)
            attr = '_revid'
        return super(WikibasePage, self).__delattr__(attr)

    def namespace(self):
        """
        Return the number of the namespace of the entity.

        @return: Namespace id
        @rtype: int
        """
        return self._namespace.id

    def exists(self):
        """
        Determine if an entity exists in the data repository.

        @rtype: bool
        """
        if not hasattr(self, '_content'):
            try:
                self.get(get_redirect=True)
                return True
            except pywikibot.NoPage:
                return False
        return 'lastrevid' in self._content

    def botMayEdit(self):
        """
        Return whether bots may edit this page.

        Because there is currently no system to mark a page that it shouldn't
        be edited by bots on Wikibase pages it always returns True. The content
        of the page is not text but a dict, the original way (to search for a
        template) doesn't apply.

        @return: True
        @rtype: bool
        """
        return True

    def get(self, force=False, *args, **kwargs):
        """
        Fetch all page data, and cache it.

        @param force: override caching
        @type force: bool
        @raise NotImplementedError: a value in args or kwargs
        """
        if args or kwargs:
            raise NotImplementedError(
                '{0}.get does not implement var args: {1!r} and {2!r}'.format(
                    self.__class__, args, kwargs))

        lazy_loading_id = not hasattr(self, 'id') and hasattr(self, '_site')
        if force or not hasattr(self, '_content'):
            identification = self._defined_by()
            if not identification:
                raise pywikibot.NoPage(self)

            try:
                data = self.repo.loadcontent(identification)
            except APIError as err:
                if err.code == 'no-such-entity':
                    raise pywikibot.NoPage(self)
                raise
            item_index = list(data.keys())[0]
            if lazy_loading_id or item_index != '-1':
                self.id = item_index

            self._content = data[item_index]
        if 'lastrevid' in self._content:
            self.latest_revision_id = self._content['lastrevid']
        else:
            if lazy_loading_id:
                p = Page(self._site, self._title)
                if not p.exists():
                    raise pywikibot.NoPage(p)
            raise pywikibot.NoPage(self)

        if 'pageid' in self._content:
            self._pageid = self._content['pageid']

        # aliases
        self.aliases = {}
        if 'aliases' in self._content:
            for lang in self._content['aliases']:
                self.aliases[lang] = []
                for value in self._content['aliases'][lang]:
                    self.aliases[lang].append(value['value'])

        # labels
        self.labels = {}
        if 'labels' in self._content:
            for lang in self._content['labels']:
                if 'removed' not in self._content['labels'][lang]:  # Bug T56767
                    self.labels[lang] = self._content['labels'][lang]['value']

        # descriptions
        self.descriptions = {}
        if 'descriptions' in self._content:
            for lang in self._content['descriptions']:
                self.descriptions[lang] = self._content[
                    'descriptions'][lang]['value']

        # claims
        self.claims = {}
        if 'claims' in self._content:
            for pid in self._content['claims']:
                self.claims[pid] = []
                for claim in self._content['claims'][pid]:
                    c = Claim.fromJSON(self.repo, claim)
                    c.on_item = self
                    self.claims[pid].append(c)

        return {'aliases': self.aliases,
                'labels': self.labels,
                'descriptions': self.descriptions,
                'claims': self.claims,
                }

    def _diff_to(self, type_key, key_name, value_name, diffto, data):
        assert type_key not in data, 'Key type must be defined in data'
        source = self._normalizeLanguages(getattr(self, type_key)).copy()
        diffto = {} if not diffto else diffto.get(type_key, {})
        new = set(source.keys())
        for key in diffto:
            if key in new:
                if source[key] == diffto[key][value_name]:
                    del source[key]
            else:
                source[key] = ''
        for key, value in source.items():
            source[key] = {key_name: key, value_name: value}
        if source:
            data[type_key] = source

    def toJSON(self, diffto=None):
        """
        Create JSON suitable for Wikibase API.

        When diffto is provided, JSON representing differences
        to the provided data is created.

        @param diffto: JSON containing claim data
        @type diffto: dict

        @rtype: dict
        """
        data = {}
        self._diff_to('labels', 'language', 'value', diffto, data)

        self._diff_to('descriptions', 'language', 'value', diffto, data)

        aliases = self._normalizeLanguages(self.aliases).copy()
        if diffto and 'aliases' in diffto:
            for lang in set(diffto['aliases'].keys()) - set(aliases.keys()):
                aliases[lang] = []
        for lang, strings in list(aliases.items()):
            if diffto and 'aliases' in diffto and lang in diffto['aliases']:
                empty = len(diffto['aliases'][lang]) - len(strings)
                if empty > 0:
                    strings += [''] * empty
                elif Counter(val['value'] for val
                             in diffto['aliases'][lang]) == Counter(strings):
                    del aliases[lang]
            if lang in aliases:
                aliases[lang] = [{'language': lang, 'value': i} for i in strings]

        if aliases:
            data['aliases'] = aliases

        claims = {}
        for prop in self.claims:
            if len(self.claims[prop]) > 0:
                claims[prop] = [claim.toJSON() for claim in self.claims[prop]]

        if diffto and 'claims' in diffto:
            temp = defaultdict(list)
            claim_ids = set()

            diffto_claims = diffto['claims']

            for prop in claims:
                for claim in claims[prop]:
                    if (prop not in diffto_claims or
                            claim not in diffto_claims[prop]):
                        temp[prop].append(claim)

                    claim_ids.add(claim['id'])

            for prop, prop_claims in diffto_claims.items():
                for claim in prop_claims:
                    if 'id' in claim and claim['id'] not in claim_ids:
                        temp[prop].append({'id': claim['id'], 'remove': ''})

            claims = temp

        if claims:
            data['claims'] = claims
        return data

    def getID(self, numeric=False, force=False):
        """
        Get the entity identifier.

        @param numeric: Strip the first letter and return an int
        @type numeric: bool
        @param force: Force an update of new data
        @type force: bool
        """
        if not hasattr(self, 'id') or force:
            self.get(force=force)
        if numeric:
            return int(self.id[1:]) if self.id != '-1' else -1

        return self.id

    @classmethod
    def is_valid_id(cls, entity_id):
        """
        Whether the string can be a valid id of the entity type.

        @param entity_id: The ID to test.
        @type entity_id: basestring

        @rtype: bool
        """
        if not hasattr(cls, 'title_pattern'):
            return True

        return bool(re.match(cls.title_pattern, entity_id))

    @property
    def latest_revision_id(self):
        """
        Get the revision identifier for the most recent revision of the entity.

        @rtype: long
        """
        if not hasattr(self, '_revid'):
            self.get()
        return self._revid

    @latest_revision_id.setter
    def latest_revision_id(self, value):
        self._revid = value

    @latest_revision_id.deleter
    def latest_revision_id(self):
        self.clear_cache()

    @staticmethod
    def _normalizeLanguages(data):
        """
        Helper function to replace site objects with their language codes.

        @param data: The dict to normalize.
        @type data: dict

        @return: the altered dict from parameter data.
        @rtype: dict
        """
        for key in data:
            if isinstance(key, pywikibot.site.BaseSite):
                data[key.lang] = data[key]
                del data[key]
        return data

    @classmethod
    def _normalizeData(cls, data):
        """
        Helper function to expand data into the Wikibase API structure.

        @param data: The dict to normalize
        @type data: dict

        @return: the altered dict from parameter data.
        @rtype: dict
        """
        for prop in ('labels', 'descriptions'):
            if prop not in data:
                continue
            data[prop] = cls._normalizeLanguages(data[prop])
            for key, value in data[prop].items():
                if isinstance(value, basestring):
                    data[prop][key] = {'language': key, 'value': value}

        if 'aliases' in data:
            for key, values in data['aliases'].items():
                if (isinstance(values, list) and
                        isinstance(values[0], basestring)):
                    data['aliases'][key] = [{'language': key, 'value': value}
                                            for value in values]

        return data

    def getdbName(self, site):
        """
        Helper function to obtain a dbName for a Site.

        @param site: The site to look up.
        @type site: Site
        """
        if isinstance(site, pywikibot.site.BaseSite):
            return site.dbName()
        return site

    @allow_asynchronous
    def editEntity(self, data=None, **kwargs):
        """
        Edit an entity using Wikibase wbeditentity API.

        This function is wrapped around by:
         - editLabels
         - editDescriptions
         - editAliases
         - ItemPage.setSitelinks

        @param data: Data to be saved
        @type data: dict, or None to save the current content of the entity.
        @keyword asynchronous: if True, launch a separate thread to edit
            asynchronously
        @type asynchronous: bool
        @keyword callback: a callable object that will be called after the entity
            has been updated. It must take two arguments: (1) a WikibasePage
            object, and (2) an exception instance, which will be None if the
            page was saved successfully. This is intended for use by bots that
            need to keep track of which saves were successful.
        @type callback: callable
        """
        if hasattr(self, '_revid'):
            baserevid = self.latest_revision_id
        else:
            baserevid = None

        if data is None:
            data = self.toJSON(diffto=(self._content if hasattr(self, '_content') else None))
        else:
            data = WikibasePage._normalizeData(data)

        updates = self.repo.editEntity(self._defined_by(singular=True), data,
                                       baserevid=baserevid, **kwargs)
        self.latest_revision_id = updates['entity']['lastrevid']

        lazy_loading_id = not hasattr(self, 'id') and hasattr(self, '_site')
        if lazy_loading_id or self.id == '-1':
            self.__init__(self.site, title=updates['entity']['id'])

        self._content = updates['entity']
        self.get()

    def editLabels(self, labels, **kwargs):
        """
        Edit entity labels.

        Labels should be a dict, with the key
        as a language or a site object. The
        value should be the string to set it to.
        You can set it to '' to remove the label.
        """
        data = {'labels': labels}
        self.editEntity(data, **kwargs)

    def editDescriptions(self, descriptions, **kwargs):
        """
        Edit entity descriptions.

        Descriptions should be a dict, with the key
        as a language or a site object. The
        value should be the string to set it to.
        You can set it to '' to remove the description.
        """
        data = {'descriptions': descriptions}
        self.editEntity(data, **kwargs)

    def editAliases(self, aliases, **kwargs):
        """
        Edit entity aliases.

        Aliases should be a dict, with the key
        as a language or a site object. The
        value should be a list of strings.
        """
        data = {'aliases': aliases}
        self.editEntity(data, **kwargs)

    def set_redirect_target(self, target_page, create=False, force=False,
                            keep_section=False, save=True, **kwargs):
        """
        Set target of a redirect for a Wikibase page.

        Has not been implemented in the Wikibase API yet, except for ItemPage.
        """
        raise NotImplementedError


class ItemPage(WikibasePage):

    """
    Wikibase entity of type 'item'.

    A Wikibase item may be defined by either a 'Q' id (qid),
    or by a site & title.

    If an item is defined by site & title, once an item's qid has
    been looked up, the item is then defined by the qid.
    """

    entity_type = 'item'
    title_pattern = r'^(Q[1-9]\d*|-1)$'

    def __init__(self, site, title=None, ns=None):
        """
        Constructor.

        @param site: data repository
        @type site: pywikibot.site.DataSite
        @param title: id number of item, "Q###",
                      -1 or None for an empty item.
        @type title: str
        @type ns: namespace
        @type ns: Namespace instance, or int, or None
            for default item_namespace
        """
        if ns is None:
            ns = site.item_namespace
        # Special case for empty item.
        if title is None or title == '-1':
            super(ItemPage, self).__init__(site, u'-1', ns=ns)
            assert self.id == '-1'
            return

        # we don't want empty titles
        if not title:
            raise pywikibot.InvalidTitle("Item's title cannot be empty")

        super(ItemPage, self).__init__(site, title, ns=ns)

        assert self.id == self._link.title

    def title(self, **kwargs):
        """
        Return ID as title of the ItemPage.

        If the ItemPage was lazy-loaded via ItemPage.fromPage, this method
        will fetch the wikibase item ID for the page, potentially raising
        NoPage with the page on the linked wiki if it does not exist, or
        does not have a corresponding wikibase item ID.

        This method also refreshes the title if the id property was set.
        i.e. item.id = 'Q60'

        All optional keyword parameters are passed to the superclass.
        """
        # If instantiated via ItemPage.fromPage using site and title,
        # _site and _title exist, and id does not exist.
        lazy_loading_id = not hasattr(self, 'id') and hasattr(self, '_site')

        if lazy_loading_id or self._link._text != self.id:
            # If the item is lazy loaded or has been modified,
            # _link._text is stale. Removing _link._title
            # forces Link to re-parse ._text into ._title.
            if hasattr(self._link, '_title'):
                del self._link._title
            self._link._text = self.getID()
            self._link.parse()
            # Remove the temporary values that are no longer needed after
            # the .getID() above has called .get(), which populated .id
            if hasattr(self, '_site'):
                del self._title
                del self._site

        return super(ItemPage, self).title(**kwargs)

    @classmethod
    def fromPage(cls, page, lazy_load=False):
        """
        Get the ItemPage for a Page that links to it.

        @param page: Page to look for corresponding data item
        @type page: pywikibot.Page
        @param lazy_load: Do not raise NoPage if either page or corresponding
                          ItemPage does not exist.
        @type lazy_load: bool
        @rtype: ItemPage

        @raise NoPage: There is no corresponding ItemPage for the page
        @raise WikiBaseError: The site of the page has no data repository.
        """
        if not page.site.has_data_repository:
            raise pywikibot.WikiBaseError('{0} has no data repository'
                                          ''.format(page.site))
        if not lazy_load and not page.exists():
            raise pywikibot.NoPage(page)

        repo = page.site.data_repository()
        if hasattr(page,
                   '_pageprops') and page.properties().get('wikibase_item'):
            # If we have already fetched the pageprops for something else,
            # we already have the id, so use it
            return cls(repo, page.properties().get('wikibase_item'))
        i = cls(repo)
        # clear id, and temporarily store data needed to lazy loading the item
        del i.id
        i._site = page.site
        i._title = page.title(withSection=False)
        if not lazy_load and not i.exists():
            raise pywikibot.NoPage(i)
        return i

    @classmethod
    def from_entity_uri(cls, site, uri, lazy_load=False):
        """
        Get the ItemPage from its entity uri.

        @param site: The Wikibase site for the item.
        @type site: pywikibot.site.DataSite
        @param uri: Entity uri for the Wikibase item.
        @type uri: basestring
        @param lazy_load: Do not raise NoPage if ItemPage does not exist.
        @type lazy_load: bool
        @rtype: ItemPage

        @raise TypeError: Site is not a valid DataSite.
        @raise ValueError: Site does not match the base of the provided uri.
        @raise NoPage: Uri points to non-existent item.
        """
        if not isinstance(site, DataSite):
            raise TypeError('{0} is not a data repository.'.format(site))

        base_uri, _, qid = uri.rpartition('/')
        if base_uri != site.concept_base_uri.rstrip('/'):
            raise ValueError(
                'The supplied data repository ({repo}) does not correspond to '
                'that of the item ({item})'.format(
                    repo=site.concept_base_uri.rstrip('/'),
                    item=base_uri))

        item = cls(site, qid)
        if not lazy_load and not item.exists():
            raise pywikibot.NoPage(item)

        return item

    def get(self, force=False, get_redirect=False, *args, **kwargs):
        """
        Fetch all item data, and cache it.

        @param force: override caching
        @type force: bool
        @param get_redirect: return the item content, do not follow the
                             redirect, do not raise an exception.
        @type get_redirect: bool
        @raise NotImplementedError: a value in args or kwargs
        """
        data = super(ItemPage, self).get(force, *args, **kwargs)

        if self.isRedirectPage() and not get_redirect:
            raise pywikibot.IsRedirectPage(self)

        # sitelinks
        self.sitelinks = {}
        if 'sitelinks' in self._content:
            for dbname in self._content['sitelinks']:
                self.sitelinks[dbname] = self._content[
                    'sitelinks'][dbname]['title']

        data['sitelinks'] = self.sitelinks
        return data

    @need_version('1.28-wmf.23')
    def concept_uri(self):
        """Return the full concept URI."""
        return '{0}{1}'.format(self.site.concept_base_uri, self.id)

    def getRedirectTarget(self):
        """Return the redirect target for this page."""
        target = super(ItemPage, self).getRedirectTarget()
        cmodel = target.content_model
        if cmodel != 'wikibase-item':
            raise pywikibot.Error(u'%s has redirect target %s with content '
                                  u'model %s instead of wikibase-item' %
                                  (self, target, cmodel))
        return self.__class__(target.site, target.title(), target.namespace())

    def toJSON(self, diffto=None):
        """
        Create JSON suitable for Wikibase API.

        When diffto is provided, JSON representing differences
        to the provided data is created.

        @param diffto: JSON containing claim data
        @type diffto: dict

        @rtype: dict
        """
        data = super(ItemPage, self).toJSON(diffto=diffto)

        self._diff_to('sitelinks', 'site', 'title', diffto, data)

        return data

    def iterlinks(self, family=None):
        """
        Iterate through all the sitelinks.

        @param family: string/Family object which represents what family of
                       links to iterate
        @type family: str|pywikibot.family.Family
        @return: iterator of pywikibot.Page objects
        @rtype: iterator
        """
        if not hasattr(self, 'sitelinks'):
            self.get()
        if family is not None and not isinstance(family, Family):
            family = Family.load(family)
        for dbname in self.sitelinks:
            pg = Page(pywikibot.site.APISite.fromDBName(dbname),
                      self.sitelinks[dbname])
            if family is None or family == pg.site.family:
                yield pg

    def getSitelink(self, site, force=False):
        """
        Return the title for the specific site.

        If the item doesn't have that language, raise NoPage.

        @param site: Site to find the linked page of.
        @type site: pywikibot.Site or database name
        @param force: override caching

        @rtype: unicode
        """
        if force or not hasattr(self, '_content'):
            self.get(force=force)
        dbname = self.getdbName(site)
        if dbname not in self.sitelinks:
            raise pywikibot.NoPage(self)
        else:
            return self.sitelinks[dbname]

    def setSitelink(self, sitelink, **kwargs):
        """
        Set sitelinks. Calls setSitelinks().

        A sitelink can either be a Page object,
        or a {'site':dbname,'title':title} dictionary.
        """
        self.setSitelinks([sitelink], **kwargs)

    def removeSitelink(self, site, **kwargs):
        """
        Remove a sitelink.

        A site can either be a Site object, or it can be a dbName.
        """
        self.removeSitelinks([site], **kwargs)

    def removeSitelinks(self, sites, **kwargs):
        """
        Remove sitelinks.

        Sites should be a list, with values either
        being Site objects, or dbNames.
        """
        data = []
        for site in sites:
            site = self.getdbName(site)
            data.append({'site': site, 'title': ''})
        self.setSitelinks(data, **kwargs)

    def setSitelinks(self, sitelinks, **kwargs):
        """
        Set sitelinks.

        Sitelinks should be a list. Each item in the
        list can either be a Page object, or a dict
        with a value for 'site' and 'title'.
        """
        data = {}
        for obj in sitelinks:
            if isinstance(obj, Page):
                dbName = self.getdbName(obj.site)
                data[dbName] = {'site': dbName, 'title': obj.title()}
            else:
                # TODO: Do some verification here
                dbName = obj['site']
                data[dbName] = obj
        data = {'sitelinks': data}
        self.editEntity(data, **kwargs)

    @allow_asynchronous
    def addClaim(self, claim, bot=True, **kwargs):
        """
        Add a claim to the item.

        @param claim: The claim to add
        @type claim: Claim
        @param bot: Whether to flag as bot (if possible)
        @type bot: bool
        @keyword asynchronous: if True, launch a separate thread to add claim
            asynchronously
        @type asynchronous: bool
        @keyword callback: a callable object that will be called after the
            claim has been added. It must take two arguments: (1) an ItemPage
            object, and (2) an exception instance, which will be None if the
            item was saved successfully. This is intended for use by bots that
            need to keep track of which saves were successful.
        @type callback: callable
        """
        self.repo.addClaim(self, claim, bot=bot, **kwargs)
        claim.on_item = self

    def removeClaims(self, claims, **kwargs):
        """
        Remove the claims from the item.

        @param claims: list of claims to be removed
        @type claims: list or pywikibot.Claim
        """
        # this check allows single claims to be removed by pushing them into a
        # list of length one.
        if isinstance(claims, pywikibot.Claim):
            claims = [claims]
        self.repo.removeClaims(claims, **kwargs)

    def mergeInto(self, item, **kwargs):
        """
        Merge the item into another item.

        @param item: The item to merge into
        @type item: ItemPage
        """
        data = self.repo.mergeItems(fromItem=self, toItem=item, **kwargs)
        if not data.get('success', 0):
            return
        self.latest_revision_id = data['from']['lastrevid']
        item.latest_revision_id = data['to']['lastrevid']
        if data.get('redirected', 0):
            self._isredir = True

    def set_redirect_target(self, target_page, create=False, force=False,
                            keep_section=False, save=True, **kwargs):
        """
        Make the item redirect to another item.

        You need to define an extra argument to make this work, like save=True

        @param target_page: target of the redirect, this argument is required.
        @type target_page: pywikibot.Item or string
        @param force: if true, it sets the redirect target even the page
            is not redirect.
        @type force: bool
        """
        if isinstance(target_page, basestring):
            target_page = pywikibot.ItemPage(self.repo, target_page)
        elif self.repo != target_page.repo:
            raise pywikibot.InterwikiRedirectPage(self, target_page)
        if self.exists() and not self.isRedirectPage() and not force:
            raise pywikibot.IsNotRedirectPage(self)
        if not save or keep_section or create:
            raise NotImplementedError
        self.repo.set_redirect_target(
            from_item=self, to_item=target_page)

    def isRedirectPage(self):
        """Return True if item is a redirect, False if not or not existing."""
        if hasattr(self, '_content') and not hasattr(self, '_isredir'):
            self._isredir = self.id != self._content.get('id', self.id)
            return self._isredir
        return super(ItemPage, self).isRedirectPage()

    # alias for backwards compatibility
    concept_url = redirect_func(concept_uri, old_name='concept_url',
                                class_name='ItemPage')


class Property(object):

    """
    A Wikibase property.

    While every Wikibase property has a Page on the data repository,
    this object is for when the property is used as part of another concept
    where the property is not _the_ Page of the property.

    For example, a claim on an ItemPage has many property attributes, and so
    it subclasses this Property class, but a claim does not have Page like
    behaviour and semantics.
    """

    types = {'wikibase-item': ItemPage,
             # 'wikibase-property': PropertyPage, must be declared first
             'string': basestring,
             'commonsMedia': FilePage,
             'globe-coordinate': pywikibot.Coordinate,
             'url': basestring,
             'time': pywikibot.WbTime,
             'quantity': pywikibot.WbQuantity,
             'monolingualtext': pywikibot.WbMonolingualText,
             'math': basestring,
             'external-id': basestring,
             'geo-shape': pywikibot.WbGeoShape,
             'tabular-data': pywikibot.WbTabularData,
             }

    value_types = {'wikibase-item': 'wikibase-entityid',
                   'wikibase-property': 'wikibase-entityid',
                   'commonsMedia': 'string',
                   'url': 'string',
                   'globe-coordinate': 'globecoordinate',
                   'math': 'string',
                   'external-id': 'string',
                   'geo-shape': 'string',
                   'tabular-data': 'string',
                   }

    def __init__(self, site, id, datatype=None):
        """
        Constructor.

        @param site: data repository
        @type site: pywikibot.site.DataSite
        @param id: id of the property
        @type id: basestring
        @param datatype: datatype of the property;
            if not given, it will be queried via the API
        @type datatype: basestring
        """
        self.repo = site
        self.id = id.upper()
        if datatype:
            self._type = datatype

    @property
    def type(self):
        """
        Return the type of this property.

        @rtype: str
        """
        if not hasattr(self, '_type'):
            self._type = self.repo.getPropertyType(self)
        return self._type

    @deprecated("Property.type")
    def getType(self):
        """
        Return the type of this property.

        It returns 'globecoordinate' for type 'globe-coordinate'
        in order to be backwards compatible. See
        https://gerrit.wikimedia.org/r/#/c/135405/ for background.
        """
        if self.type == 'globe-coordinate':
            return 'globecoordinate'
        else:
            return self._type

    def getID(self, numeric=False):
        """
        Get the identifier of this property.

        @param numeric: Strip the first letter and return an int
        @type numeric: bool
        """
        if numeric:
            return int(self.id[1:])
        else:
            return self.id


class PropertyPage(WikibasePage, Property):

    """
    A Wikibase entity in the property namespace.

    Should be created as::

        PropertyPage(DataSite, 'P21')
    """

    entity_type = 'property'
    title_pattern = r'^P[1-9]\d*$'

    def __init__(self, source, title=u""):
        """
        Constructor.

        @param source: data repository property is on
        @type source: pywikibot.site.DataSite
        @param title: page name of property, like "P##"
        @type title: str
        """
        if not title:
            raise pywikibot.InvalidTitle("Property's title cannot be empty")

        WikibasePage.__init__(self, source, title,
                              ns=source.property_namespace)
        Property.__init__(self, source, self.id)

    def get(self, force=False, *args, **kwargs):
        """
        Fetch the property entity, and cache it.

        @param force: override caching
        @type force: bool
        @raise NotImplementedError: a value in args or kwargs
        """
        if args or kwargs:
            raise NotImplementedError(
                'PropertyPage.get only implements "force".')

        data = WikibasePage.get(self, force)
        if 'datatype' in self._content:
            self._type = self._content['datatype']
        data['datatype'] = self._type
        return data

    def newClaim(self, *args, **kwargs):
        """
        Helper function to create a new claim object for this property.

        @rtype: Claim
        """
        return Claim(self.site, self.getID(), datatype=self.type,
                     *args, **kwargs)


# Add PropertyPage to the class attribute "types" after its declaration.
Property.types['wikibase-property'] = PropertyPage


class Claim(Property):

    """
    A Claim on a Wikibase entity.

    Claims are standard claims as well as references and qualifiers.
    """

    TARGET_CONVERTER = {
        'wikibase-item': lambda value, site:
            ItemPage(site, 'Q' + str(value['numeric-id'])),
        'wikibase-property': lambda value, site:
            PropertyPage(site, 'P' + str(value['numeric-id'])),
        'commonsMedia': lambda value, site:
            FilePage(pywikibot.Site('commons', 'commons'), value),  # T90492
        'globe-coordinate': pywikibot.Coordinate.fromWikibase,
        'geo-shape': pywikibot.WbGeoShape.fromWikibase,
        'tabular-data': pywikibot.WbTabularData.fromWikibase,
        'time': pywikibot.WbTime.fromWikibase,
        'quantity': pywikibot.WbQuantity.fromWikibase,
        'monolingualtext': lambda value, site:
            pywikibot.WbMonolingualText.fromWikibase(value)
    }

    SNAK_TYPES = ('value', 'somevalue', 'novalue')

    def __init__(self, site, pid, snak=None, hash=None, isReference=False,
                 isQualifier=False, **kwargs):
        """
        Constructor.

        Defined by the "snak" value, supplemented by site + pid

        @param site: repository the claim is on
        @type site: pywikibot.site.DataSite
        @param pid: property id, with "P" prefix
        @param snak: snak identifier for claim
        @param hash: hash identifier for references
        @param isReference: whether specified claim is a reference
        @param isQualifier: whether specified claim is a qualifier
        """
        Property.__init__(self, site, pid, **kwargs)
        self.snak = snak
        self.hash = hash
        self.isReference = isReference
        self.isQualifier = isQualifier
        if self.isQualifier and self.isReference:
            raise ValueError(u'Claim cannot be both a qualifier and reference.')
        self.sources = []
        self.qualifiers = OrderedDict()
        self.target = None
        self.snaktype = 'value'
        self.rank = 'normal'
        self.on_item = None  # The item it's on

    @classmethod
    def fromJSON(cls, site, data):
        """
        Create a claim object from JSON returned in the API call.

        @param data: JSON containing claim data
        @type data: dict

        @rtype: Claim
        """
        claim = cls(site, data['mainsnak']['property'],
                    datatype=data['mainsnak'].get('datatype', None))
        if 'id' in data:
            claim.snak = data['id']
        elif 'hash' in data:
            claim.hash = data['hash']
        claim.snaktype = data['mainsnak']['snaktype']
        if claim.getSnakType() == 'value':
            value = data['mainsnak']['datavalue']['value']
            # The default covers string, url types
            claim.target = Claim.TARGET_CONVERTER.get(
                claim.type, lambda value, site: value)(value, site)
        if 'rank' in data:  # References/Qualifiers don't have ranks
            claim.rank = data['rank']
        if 'references' in data:
            for source in data['references']:
                claim.sources.append(cls.referenceFromJSON(site, source))
        if 'qualifiers' in data:
            for prop in data['qualifiers-order']:
                claim.qualifiers[prop] = [cls.qualifierFromJSON(site, qualifier)
                                          for qualifier in data['qualifiers'][prop]]
        return claim

    @classmethod
    def referenceFromJSON(cls, site, data):
        """
        Create a dict of claims from reference JSON returned in the API call.

        Reference objects are represented a
        bit differently, and require some
        more handling.

        @rtype: dict
        """
        source = OrderedDict()

        # Before #84516 Wikibase did not implement snaks-order.
        # https://gerrit.wikimedia.org/r/#/c/84516/
        if 'snaks-order' in data:
            prop_list = data['snaks-order']
        else:
            prop_list = data['snaks'].keys()

        for prop in prop_list:
            for claimsnak in data['snaks'][prop]:
                claim = cls.fromJSON(site, {'mainsnak': claimsnak,
                                            'hash': data['hash']})
                claim.isReference = True
                if claim.getID() not in source:
                    source[claim.getID()] = []
                source[claim.getID()].append(claim)
        return source

    @classmethod
    def qualifierFromJSON(cls, site, data):
        """
        Create a Claim for a qualifier from JSON.

        Qualifier objects are represented a bit
        differently like references, but I'm not
        sure if this even requires it's own function.

        @rtype: Claim
        """
        claim = cls.fromJSON(site, {'mainsnak': data,
                                    'hash': data['hash']})
        claim.isQualifier = True
        return claim

    def toJSON(self):
        """
        Create dict suitable for the MediaWiki API.

        @rtype: dict
        """
        data = {
            'mainsnak': {
                'snaktype': self.snaktype,
                'property': self.getID()
            },
            'type': 'statement'
        }
        if hasattr(self, 'snak') and self.snak is not None:
            data['id'] = self.snak
        if hasattr(self, 'rank') and self.rank is not None:
            data['rank'] = self.rank
        if self.getSnakType() == 'value':
            data['mainsnak']['datatype'] = self.type
            data['mainsnak']['datavalue'] = self._formatDataValue()
        if self.isQualifier or self.isReference:
            data = data['mainsnak']
            if hasattr(self, 'hash') and self.hash is not None:
                data['hash'] = self.hash
        else:
            if len(self.qualifiers) > 0:
                data['qualifiers'] = {}
                data['qualifiers-order'] = list(self.qualifiers.keys())
                for prop, qualifiers in self.qualifiers.items():
                    for qualifier in qualifiers:
                        assert qualifier.isQualifier is True
                    data['qualifiers'][prop] = [qualifier.toJSON() for qualifier in qualifiers]
            if len(self.sources) > 0:
                data['references'] = []
                for collection in self.sources:
                    reference = {'snaks': {}, 'snaks-order': list(collection.keys())}
                    for prop, val in collection.items():
                        reference['snaks'][prop] = []
                        for source in val:
                            assert source.isReference is True
                            src_data = source.toJSON()
                            if 'hash' in src_data:
                                if 'hash' not in reference:
                                    reference['hash'] = src_data['hash']
                                del src_data['hash']
                            reference['snaks'][prop].append(src_data)
                    data['references'].append(reference)
        return data

    def setTarget(self, value):
        """
        Set the target value in the local object.

        @param value: The new target value.
        @type value: object

        @exception ValueError: if value is not of the type
            required for the Claim type.
        """
        value_class = self.types[self.type]
        if not isinstance(value, value_class):
            raise ValueError("%s is not type %s."
                             % (value, value_class))
        self.target = value

    def changeTarget(self, value=None, snaktype='value', **kwargs):
        """
        Set the target value in the data repository.

        @param value: The new target value.
        @type value: object
        @param snaktype: The new snak type.
        @type snaktype: str ('value', 'somevalue', or 'novalue')
        """
        if value:
            self.setTarget(value)

        data = self.repo.changeClaimTarget(self, snaktype=snaktype,
                                           **kwargs)
        # TODO: Re-create the entire item from JSON, not just id
        self.snak = data['claim']['id']
        self.on_item.latest_revision_id = data['pageinfo']['lastrevid']

    def getTarget(self):
        """
        Return the target value of this Claim.

        None is returned if no target is set

        @return: object
        """
        return self.target

    def getSnakType(self):
        """
        Return the type of snak.

        @return: str ('value', 'somevalue' or 'novalue')
        @rtype: unicode
        """
        return self.snaktype

    def setSnakType(self, value):
        """
        Set the type of snak.

        @param value: Type of snak
        @type value: str ('value', 'somevalue', or 'novalue')
        """
        if value in self.SNAK_TYPES:
            self.snaktype = value
        else:
            raise ValueError(
                "snaktype must be 'value', 'somevalue', or 'novalue'.")

    def getRank(self):
        """Return the rank of the Claim."""
        return self.rank

    def setRank(self, rank):
        """Set the rank of the Claim."""
        self.rank = rank

    def changeRank(self, rank):
        """Change the rank of the Claim and save."""
        self.rank = rank
        return self.repo.save_claim(self)

    def changeSnakType(self, value=None, **kwargs):
        """
        Save the new snak value.

        TODO: Is this function really needed?
        """
        if value:
            self.setSnakType(value)
        self.changeTarget(snaktype=self.getSnakType(), **kwargs)

    def getSources(self):
        """
        Return a list of sources, each being a list of Claims.

        @rtype: list
        """
        return self.sources

    def addSource(self, claim, **kwargs):
        """
        Add the claim as a source.

        @param claim: the claim to add
        @type claim: pywikibot.Claim
        """
        self.addSources([claim], **kwargs)

    def addSources(self, claims, **kwargs):
        """
        Add the claims as one source.

        @param claims: the claims to add
        @type claims: list of pywikibot.Claim
        """
        data = self.repo.editSource(self, claims, new=True, **kwargs)
        self.on_item.latest_revision_id = data['pageinfo']['lastrevid']
        source = defaultdict(list)
        for claim in claims:
            claim.hash = data['reference']['hash']
            source[claim.getID()].append(claim)
        self.sources.append(source)

    def removeSource(self, source, **kwargs):
        """
        Remove the source. Call removeSources().

        @param source: the source to remove
        @type source: pywikibot.Claim
        """
        self.removeSources([source], **kwargs)

    def removeSources(self, sources, **kwargs):
        """
        Remove the sources.

        @param sources: the sources to remove
        @type sources: list of pywikibot.Claim
        """
        data = self.repo.removeSources(self, sources, **kwargs)
        self.on_item.latest_revision_id = data['pageinfo']['lastrevid']
        for source in sources:
            source_dict = defaultdict(list)
            source_dict[source.getID()].append(source)
            self.sources.remove(source_dict)

    def addQualifier(self, qualifier, **kwargs):
        """Add the given qualifier.

        @param qualifier: the qualifier to add
        @type qualifier: Claim
        """
        data = self.repo.editQualifier(self, qualifier, **kwargs)
        qualifier.isQualifier = True
        self.on_item.latest_revision_id = data['pageinfo']['lastrevid']
        if qualifier.getID() in self.qualifiers:
            self.qualifiers[qualifier.getID()].append(qualifier)
        else:
            self.qualifiers[qualifier.getID()] = [qualifier]

    def removeQualifier(self, qualifier, **kwargs):
        """
        Remove the qualifier. Call removeQualifiers().

        @param qualifier: the qualifier to remove
        @type qualifier: Claim
        """
        self.removeQualifiers([qualifier], **kwargs)

    def removeQualifiers(self, qualifiers, **kwargs):
        """
        Remove the qualifiers.

        @param qualifiers: the qualifiers to remove
        @type qualifiers: list Claim
        """
        data = self.repo.remove_qualifiers(self, qualifiers, **kwargs)
        self.on_item.latest_revision_id = data['pageinfo']['lastrevid']
        for qualifier in qualifiers:
            self.qualifiers[qualifier.getID()].remove(qualifier)

    def target_equals(self, value):
        """
        Check whether the Claim's target is equal to specified value.

        The function checks for:

        - WikibasePage ID equality
        - WbTime year equality
        - Coordinate equality, regarding precision
        - WbMonolingualText text equality
        - direct equality

        @param value: the value to compare with
        @return: true if the Claim's target is equal to the value provided,
            false otherwise
        @rtype: bool
        """
        if (isinstance(self.target, WikibasePage) and
                isinstance(value, basestring)):
            return self.target.id == value

        if (isinstance(self.target, pywikibot.WbTime) and
                not isinstance(value, pywikibot.WbTime)):
            return self.target.year == int(value)

        if (isinstance(self.target, pywikibot.Coordinate) and
                isinstance(value, basestring)):
            coord_args = [float(x) for x in value.split(',')]
            if len(coord_args) >= 3:
                precision = coord_args[2]
            else:
                precision = 0.0001  # Default value (~10 m at equator)
            try:
                if self.target.precision is not None:
                    precision = max(precision, self.target.precision)
            except TypeError:
                pass

            return (abs(self.target.lat - coord_args[0]) <= precision and
                    abs(self.target.lon - coord_args[1]) <= precision)

        if (isinstance(self.target, pywikibot.WbMonolingualText) and
                isinstance(value, basestring)):
            return self.target.text == value

        return self.target == value

    def has_qualifier(self, qualifier_id, target):
        """
        Check whether Claim contains specified qualifier.

        @param qualifier_id: id of the qualifier
        @type qualifier_id: str
        @param target: qualifier target to check presence of
        @return: true if the qualifier was found, false otherwise
        @rtype: bool
        """
        if self.isQualifier or self.isReference:
            raise ValueError(u'Qualifiers and references cannot have '
                             u'qualifiers.')

        for qualifier in self.qualifiers.get(qualifier_id, []):
            if qualifier.target_equals(target):
                return True
        return False

    def _formatValue(self):
        """
        Format the target into the proper JSON value that Wikibase wants.

        @return: JSON value
        @rtype: dict
        """
        if self.type in ('wikibase-item', 'wikibase-property'):
            value = {'entity-type': self.getTarget().entity_type,
                     'numeric-id': self.getTarget().getID(numeric=True)}
        elif self.type in ('string', 'url', 'math', 'external-id'):
            value = self.getTarget()
        elif self.type == 'commonsMedia':
            value = self.getTarget().title(withNamespace=False)
        elif self.type in ('globe-coordinate', 'time',
                           'quantity', 'monolingualtext',
                           'geo-shape', 'tabular-data'):
            value = self.getTarget().toWikibase()
        else:
            raise NotImplementedError('%s datatype is not supported yet.'
                                      % self.type)
        return value

    def _formatDataValue(self):
        """
        Format the target into the proper JSON datavalue that Wikibase wants.

        @return: Wikibase API representation with type and value.
        @rtype: dict
        """
        return {'value': self._formatValue(),
                'type': self.value_types.get(self.type, self.type)
                }


class Revision(DotReadableDict):

    """A structure holding information about a single revision of a Page."""

    HistEntry = namedtuple('HistEntry', ['revid',
                                         'timestamp',
                                         'user',
                                         'comment'])

    FullHistEntry = namedtuple('FullHistEntry', ['revid',
                                                 'timestamp',
                                                 'user',
                                                 'text',
                                                 'rollbacktoken'])

    def __init__(self, revid, timestamp, user, anon=False, comment=u"",
                 text=None, minor=False, rollbacktoken=None, parentid=None,
                 contentmodel=None, sha1=None, page=None):
        """
        Constructor.

        All parameters correspond to object attributes (e.g., revid
        parameter is stored as self.revid)

        @param revid: Revision id number
        @type revid: int
        @param text: Revision wikitext.
        @type text: unicode, or None if text not yet retrieved
        @param timestamp: Revision time stamp
        @type timestamp: pywikibot.Timestamp
        @param user: user who edited this revision
        @type user: unicode
        @param anon: user is unregistered
        @type anon: bool
        @param comment: edit comment text
        @type comment: unicode
        @param minor: edit flagged as minor
        @type minor: bool
        @param rollbacktoken: rollback token
        @type rollbacktoken: unicode
        @param parentid: id of parent Revision (v1.16+)
        @type parentid: long
        @param contentmodel: content model label (v1.21+)
        @type contentmodel: unicode
        @param sha1: sha1 of revision text (v1.19+)
        @type sha1: unicode
        """
        self.revid = revid
        self._text = text
        self.timestamp = timestamp
        self.user = user
        self.anon = anon
        self._comment = comment
        self.minor = minor
        self._token = rollbacktoken
        self._parent_id = parentid
        self._content_model = contentmodel
        self._sha1 = sha1
        self._page = page

    @classmethod
    def from_API(cls, rev, page):
        # TODO: T102735: Use the page content model for <1.21
        revision = Revision(
            revid=rev['revid'],
            timestamp=pywikibot.Timestamp.fromISOformat(rev['timestamp']),
            user=rev.get('user'),
            anon='anon' in rev,
            minor='minor' in rev,
            parentid=rev['parentid'],
            contentmodel=rev.get('contentmodel', None),
            sha1=rev.get('sha1', None),
            page=page,
        )
        revision._set_values(rev)
        return revision

    def _set_values(self, rev):
        if 'comment' in rev:
            self._comment = rev['comment']
        if '*' in rev:
            self._text = rev['*']
        if 'rollbacktoken' in rev:
            self._token = rev['rollbacktoken']

    def _get_revision(self, **params):
        if not self._page:
            raise TypeError('The revision instance ({0}) was not initalized to '
                            'allow getting the remaining values afterwards.')
        req = pywikibot.data.api.Request(
            site=self._page.site, action='query', prop='revisions',
            revids=self.revid, **params)
        revision = next(iter(req.submit()['query']['pages'].values()))['revisions'][0]
        assert(revision['revid'] == self.revid)
        return revision

    def _get_all(self):
        """Get all values for this revision."""
        revision = self._get_revision(rvprop='ids|comment|content')
        self._comment = revision['comment']
        self._text = revision['*']

    @property
    def parent_id(self):
        """
        Return id of parent/previous revision.

        Returns 0 if there is no previous revision

        @return: id of parent/previous revision
        @rtype: int or long
        @raises AssertionError: parent id not supplied to the constructor
        """
        if self._parent_id is None:
            raise AssertionError(
                'Revision %d was instantiated without a parent id'
                % self.revid)

        return self._parent_id

    @property
    def content_model(self):
        """
        Return content model of the revision.

        @return: content model
        @rtype: str
        @raises AssertionError: content model not supplied to the constructor
            which always occurs for MediaWiki versions lower than 1.21.
        """
        # TODO: T102735: Add a sane default of 'wikitext' and others for <1.21
        if self._content_model is None:
            raise AssertionError(
                'Revision %d was instantiated without a content model'
                % self.revid)

        return self._content_model

    @property
    def sha1(self):
        """
        Return and cache SHA1 checksum of the text.

        @return: if the SHA1 checksum is cached it'll be returned which is the
            case when it was requested from the API. Otherwise it'll use the
            revision's text to calculate the checksum (encoding it using UTF8
            first). That calculated checksum will be cached too and returned on
            future calls. If the text is None (not queried) it will just return
            None and does not cache anything.
        @rtype: str or None
        """
        if self._sha1 is None:
            if self.text is None:
                # No text? No sha1 then.
                return None
            self._sha1 = hashlib.sha1(self.text.encode('utf8')).hexdigest()

        return self._sha1

    @property
    def text(self):
        if not self._text:
            self._get_all()
        return self._text

    @property
    def comment(self):
        if not self._comment:
            self._get_all()
        return self._comment

    @property
    def rollbacktoken(self):
        if not self._token:
            if self._page.site.version() >= MediaWikiVersion('1.24wmf19'):
                # let site cache it
                return self._page.site.tokens['rollback']
            else:
                revision = self._get_revision(rvtoken='rollback')
                self._token = revision['rollbacktoken']
        return self._token

    def hist_entry(self):
        """Return a namedtuple with a Page history record."""
        return Revision.HistEntry(self.revid, self.timestamp, self.user,
                                  self.comment)

    def full_hist_entry(self):
        """Return a namedtuple with a Page full history record."""
        return Revision.FullHistEntry(self.revid, self.timestamp, self.user,
                                      self.text, self.rollbacktoken)


class _RevisionCache(UnicodeMixin):

    """
    A cache holding chunks of revisions.

    As not all revisions are necessaril requested in one go, it caches chunks of
    revisions. The chunks don't overlap and each chunk gets older compared to
    the previous chunk. Each revision in a chunk gets also older than the
    revision before it (in the list). There are also always revisions between
    two chunks. If there are none, both chunks get merged.

    Because the revision ID is not strictly decreasing with each older revision,
    it's using the timestamp to determine the order of chunks in the cache.
    """

    # caching the caches, reference them weakly so when there is no page using
    # it that it can be garbage collected
    _caches = defaultdict(weakref.WeakValueDictionary)

    def __init__(self, page):
        self._cache = []
        self._page = page
        # when the last time the newest revision was requested
        self._latest_revision_requested = None

    @classmethod
    def get_cache(cls, page):
        """Get the revision cache belonging to this page."""
        title = page.title(withSection=False)
        site_cache = cls._caches[page.site]
        # use get, in case the cache could get discarded after an 'in' check
        cache = site_cache.get(title)
        if cache is None:
            cache = _RevisionCache(page)
            site_cache[title] = cache
        return cache

    @staticmethod
    def _is_bigger(value, comp):
        return value and value > comp

    @staticmethod
    def _is_smaller(value, comp):
        return value and value < comp

    def __unicode__(self):
        return u'RevisionCache({0},[{1}])'.format(
            self._page.title(),
            '],['.join(
            ','.join(str(rev.revid) for rev in chunk)
            for chunk in self._cache))

    def _check_integrity(self):
        """
        Check the consistency of the cache.

        The following error codes exist:

        0. Previous' parent_id does not match current's revid. If first of
           chunk they must be unequal and otherwise they must be equal
        1. Previous' parent_id was 0 (== first revision). Suppresses code 0.
        2. Previous' timestamp is before the current's timestamp
        3. Chunk's length is 0 (index in chunk is None)

        @return: The errors with the position (chunk, index in chunk and error
            code).
        @rtype: list of tuple
        """
        errors = []
        last = None
        for i, block in enumerate(self._cache):
            if len(block) == 0:
                errors += [(i, None, 3)]
            for j, cached in enumerate(block):
                if last is not None:
                    if last.parent_id == 0:
                        errors += [(i, j, 1)]
                    elif (j > 0) == (last.parent_id != cached.revid):
                        errors += [(i, j, 0)]
                    if last.timestamp < cached.timestamp:
                        errors += [(i, j, 2)]
                last = cached
        return errors

    def _assert_integrity(self):
        """Combine check_integrity with assert, but display errors."""
        integrity = self._check_integrity()
        if integrity:
            pywikibot.error(integrity)
            assert(False)

    # TODO: ↓ move to tools
    @staticmethod
    def _keyed_func(left, a, x, key, reverse=None):
        from bisect import bisect_right as br
        from bisect import bisect_left as bl
        a = [key(e) for e in a]
        if reverse is None:
            reverse = a[0] > a[-1]
        # when reversed, then left needs bisect_right
        if left != reverse:
            func = bl
        else:
            func = br
        if reverse:
            a = a[::-1]
        idx = func(a, x)
        if reverse:
            return len(a) - idx
        else:
            return idx

    @staticmethod
    def bisect_right(a, x, key=lambda e: e, reverse=False):
        return _RevisionCache._keyed_func(False, a, x, key=key, reverse=reverse)

    @staticmethod
    def bisect_left(a, x, key=lambda e: e, reverse=False):
        return _RevisionCache._keyed_func(True, a, x, key=key, reverse=reverse)
    # TODO: ↑ move

    @staticmethod
    def _key_time(rev):
        return rev.timestamp

    @classmethod
    def _get_cached(cls, cached_block, endid, endtime, total, check):
        if not cached_block:
            return [], False
        short_block = cached_block[:total]
        until = len(short_block)
        for index in range(until):
            if cached_block[index].revid == endid:
                until = index + 1
                break
        if endtime:
            until = min(until, cls.bisect_right(short_block, endtime, key=cls._key_time, reverse=None))
        # if len(short_block) < until:
        #    print('{0} ← {1}'.format(until, len(short_block)))
        short_block = cached_block[:until]
        stopped = ((total is not None and total <= len(short_block)) or
                   cached_block[-1].parent_id == 0 or
                   short_block[-1].revid == endid)
        if until < len(short_block):
            # because multiple revisions could have the same timestamp, instead
            # the revision after that must be checked if it's after it
            stopped |= check(endtime, cached_block[until].timestamp)
        return short_block, stopped

    @staticmethod
    def _revid_index(chunk, revision_id):
        for idx, revision in enumerate(chunk):
            if revision.revid == revision_id:
                return idx
        return -1

    def _index(self, revision_id):
        """
        Return the position of a revision ID.

        If the revision is cached it returns the chunk and position in chunk.
        Otherwise it returns the False, False.
        """
        for chunk_index, chunk in enumerate(self._cache):
            idx = self._revid_index(chunk, revision_id)
            if idx >= 0:
                return chunk_index, idx
        return False, False

    def _revision_chunk_generator(self, content=False, rollback=False,
                                  is_cached=False, **kwargs):
        """
        A generator returning batches of revisions.

        This generator is useful, because all the data it yields at each point
        is already fetched. Unlike a generator which yields each revision, this
        allows to also cache revisions which were requested but not needed.
        """
        if 'revids' not in kwargs:
            kwargs['titles'] = self._page.title()
        if content:
            if is_cached:
                kwargs['rvprop'] = 'ids|comment|content'
            else:
                kwargs['rvprop'] = 'ids|flags|timestamp|user|comment|content'
        if rollback:
            kwargs['rvtoken'] = 'rollback'
            if 'rvprop' not in kwargs and is_cached:
                kwargs['rvprop'] = 'ids'
        gen = pywikibot.data.api.PropertyGenerator(
            prop='revisions', site=self._page.site, **kwargs)
        if 'revids' in kwargs:
            gen.set_maximum_items(-1)
        for page_data in gen:
            if not self._page.site.sametitle(
                    page_data['title'], self._page.title(withSection=False)):
                raise pywikibot.Error(
                    u'Query on "{0}" returned data on "{1}"'.format(
                    self._page.title(), page_data['title']))
            yield page_data['revisions']

    def _revision_generator(self, content=False, rollback=False,
                            is_cached=False, **kwargs):
        """A generator returning each revision separately."""
        for revision_set in self._revision_chunk_generator(content, rollback,
                                                           is_cached, **kwargs):
            for revision in revision_set:
                yield revision

    def get_separate_revisions(self, revids, content=False, rollback=False):
        """Get the revisions in the same order as revids."""
        def update(revs):
            # is a generator so force iteration
            list(self._fill_cached(revs, content, rollback))
        return self._cache_rev_dicts(
            revids, update,
            lambda requested: self._revision_generator(content, rollback,
                                                       revids=requested))

    def cache_revisions(self, revisions):
        """
        Cache uncached the revisions and update cached ones.

        @param revisions: The revision dictionaries returned from the API.
        @type revisions: iterable
        @return: The Revision objects converted from the dictionary.
        @rtype: list
        """
        def update(revs):
            for rev in revs:
                rev._set_values(rev_map[rev.revid])
        rev_map = dict((rev['revid'], rev) for rev in revisions)
        cached = self._cache_rev_dicts(
            rev_map, update,
            lambda requested: [rev for rev in revisions if rev['revid'] in requested])
        return cached

    def _cache_rev_dicts(self, revids, update_func, gen_func):
        """
        Yield Revision objects for the given ids and cache uncached.

        @param revids: Revision IDs of the page.
        @type revisions: iterable
        @param update_func: A function called with a generator containing
            the Revision objects which are already cached. The function can then
            fill in additional data.
        @type update_func: callable with 1 parameter
        @param gen_func: A function called with the revision IDs (a subset of
            revids) which were not cached.
        @type gen_func: callable with 1 parameter
        @return: The Revision objects in the same order as the revision IDs. IDs
            appearing multiple times will only appear once and that in the first
            place. If there was no defined order in the original revision IDs
            the resulting order is undefined.
        @rtype: list
        """
        yielded = set()
        cached = []  # buffer to yield them in order with others
        requested = {}
        # determine which revisions are already in the cache and which needed
        # to be processed
        i = []
        for revid in revids:
            if revid in yielded:
                continue
            i += [revid]
            yielded.add(revid)
            chunk, idx = self._index(revid)
            if chunk is False:
                cached += [None]
                requested[revid] = len(cached) - 1
            else:
                revision = self._cache[chunk][idx]
                assert(revision.revid == revid)
                cached += [revision]
        update_func(rev for rev in cached if rev is not None)
        revisions = [Revision.from_API(rev, self._page) for rev in gen_func(requested)]
        assert(set(rev.revid for rev in revisions) == set(requested))
        for revision in revisions:
            idx = requested[revision.revid]
            assert(cached[idx] is None)
            cached[idx] = revision

        chunks = self._rev_chains(revisions)
        # if len(chunks) > 1:
        #     print('determined {0} chunk(s) with length(s): {1}'.format(
        #           len(chunks), ', '.join(str(len(chunk)) for chunk in chunks)))
        for chunk in chunks:
            # find a chunk which preceeds it directly
            for prev_index, cached_chunk in enumerate(self._cache):
                if cached_chunk[-1].parent_id == chunk[0].revid:
                    preceeds = True
                    break
            else:
                preceeds = False
            if preceeds:
                self._cache[prev_index].extend(chunk)
            else:
                prev_index = self.bisect_left(
                    self._cache, chunk[0].timestamp,
                    key=lambda block: block[-1].timestamp, reverse=True)
            # find a chunk which follows directly
            for next_index, cached_chunk in enumerate(self._cache):
                if chunk[-1].parent_id == cached_chunk[0].revid:
                    follows = True
                    break
            else:
                follows = False
            if follows:
                if preceeds:
                    assert(next_index == prev_index + 1)
                    self._cache[prev_index].extend(self._cache.pop(next_index))
                else:
                    self._cache[prev_index] = chunk + self._cache[next_index]
            elif not preceeds:
                self._cache.insert(prev_index, chunk)
            self._assert_integrity()
        return cached

    @staticmethod
    def _rev_dict(revisions):
        """Convert a list of revisions into a dict keyed by id."""
        return dict((rev.revid, rev) for rev in revisions)

    @classmethod
    def _rev_chains(cls, revisions):
        """Return a list of chains from a list of revisions."""
        revisions = cls._rev_dict(revisions)
        chunks = {}
        # because the id might jump, it's not possible to sort and split
        # whenever parent_id != revid. e.g. 10 > 8 > 9 > 7
        while revisions:
            # pop one from the revisions
            rev = next(iter(revisions.values()))
            del revisions[rev.revid]
            chunk = [rev]
            # pop the parent revisions
            while rev.parent_id in revisions:
                rev = revisions.pop(rev.parent_id)
                chunk += [rev]
            # check whether the later part of the chunk has been already checked
            if rev.parent_id in chunks:
                assert(chunks[rev.parent_id])
                chunk += chunks[rev.parent_id]
                chunks[rev.parent_id] = False
            assert(chunk[0].revid not in chunks)
            chunks[chunk[0].revid] = chunk
        assert(all(c is False or len(c) > 0 for c in chunks.values()))
        assert(all(c[-1].parent_id not in chunks for c in chunks.values()
                   if c is not False))
        return [c for c in chunks.values() if c is not False]

    def __getitem__(self, revid):
        """Return the revision with the given id. Might do requests."""
        return self.get_separate_revisions([revid])[0]

    def __contains__(self, revid):
        """Return whether the revid is already cached."""
        return self._index(revid)[0] is not False

    def _fill_cached(self, cached, content, rollback):
        """Set content or rollback token for cached revisions without it."""
        cached = list(cached)
        # cached must have each revision ID at most once
        assert(len(set(rev.revid for rev in cached)) == len(cached))
        if self._page.site.version() >= MediaWikiVersion('1.24wmf19'):
            # in newer versions, the token is got via query+tokens
            rollback = False
        need_content = [rev.revid for rev in cached if not rev._text] if content else []
        need_rollback = [rev.revid for rev in cached if not rev._token] if rollback else []
        if need_content == need_rollback:
            # query both together
            content_gen = self._revision_chunk_generator(True, True, True,
                                                         revids=need_content)
            rollback_gen = None
        else:
            if need_content:
                content_gen = self._revision_chunk_generator(True, False, True,
                                                             revids=need_content)
            if need_rollback:
                rollback_gen = self._revision_chunk_generator(False, True, True,
                                                              revids=need_rollback)

        id_map = self._rev_dict(cached)
        # if need_content or need_rollback:
        #     print('Need: {0} // {1}'.format(need_content, need_rollback))
        for revision in cached:
            if content and not revision._text:
                for queried_rev in next(content_gen):
                    id_map[queried_rev['revid']]._set_values(queried_rev)
            # if both are got with the same query, then _token will be set via
            # the line above, and this line will conclude the token is set
            if rollback and not revision._token:
                for queried_rev in next(rollback_gen):
                    id_map[queried_rev['revid']]._set_values(queried_rev)
            assert(not content or revision._text)
            assert(not rollback or revision._token)
            yield revision

    def get_revisions(self, content=False, startid=None, endid=None,
                      starttime=None, endtime=None, reverse=False, total=None,
                      rollback=False, assume_newest=False):
        """
        Get and caches revisions.

        If neither startid or starttime is given, it will request all revisions
        until the first cached revision is returned (unless endid, endtime or
        total are stopping it first).

        It'll make assumptions about startid and endid. Because it's not
        possible to determine whether the endid or next cached id comes next
        it'll choose the number closer to the current value. In most cases this
        will select also fewer number of revisions. If this is not the case it
        might query more revisions than necessary, although it'd start issuing
        cached revisions as soon as one batch ended in one chunk.

        A similar case happens when startid which is not already cached. In such
        a case it's querying revisions until the next closest revision id
        already cached. It is possible that another chunk could be before the
        selected chunk. In that case it might request more revisions than
        actually necessary (similar to endid). Another case would be when the
        next selected chunk is actually on the other side (depending on
        reverse).When that happened the request doesn't return any revisions and
        it'll select the next chunk. This continues until it finds the first
        revision is returned.

        Because of that the start and end id must be revisions of the page.
        Otherwise it's not possible to determine where the revision starts. For
        example if a page has only even revision numbers and an odd revision
        start id is given, it can't determine whether that revision is part of
        the page (might be a new uncached revision). And if not all revisions
        are known it's not possible to determine where it fits the best (a id
        of 7 was given, 10 was selected because it was the closest cached but
        there was actually a 8).

        Because the revision IDs must not be stricly increasing over time, the
        endid doesn't need to be greater (or smaller in reverse) than the
        startid.

        @param content: Define also the content and comment for each revision.
            If the revision is cached it'll request the data and update the
            cached revisions.
        @type content: bool
        @param startid: The first revision ID to be returned. It has to be a
            revision of the page. If None (default) it'll start with the newest,
            unless a starttime is given.
        @type startid: int or None
        @param endid: The last revision ID to be returned. It has to be a
            revision of that page. If None (default) it won't stop because of
            the revision id.
        @type endid: int or None
        @param starttime: No revisions returned are created after that date. If
            None (default) it won't exclude those revisions. A string is
            interpreted as a timestamp.
        @type starttime: datetime or str or None
        @param endtime: No revisions returned are created before that date. If
            None (default) it won't exclude those revisions. A string is
            interpreted as a timestamp.
        @type endtime: datetime or None
        @param reverse: Return the revisions in reverse order, from oldest to
            newest. This will inverse the startid/starttime/endid/endtime
            arguments.
        @type reverse: bool
        @param total: The total number of revisions returned. It will return as
            many revisions as possible if None (default).
        @type total: int or None
        @param rollback: Query the rollback token for each revision. This will
            be ignored on sites with version 1.24wmf19 or newer.
        @type rollback: bool
        @param assume_newest: Assume that the first value in the cache is the
            newest revision. If it's a datetime, then the newest revision must
            have been retrieved after that datetime.
        @type assume_newest: bool or None or datetime
        """
        if startid is not None and starttime is not None:
            raise ValueError('The parameters startid and starttime may not be '
                             'set at the same time.')
        if endid is not None and endtime is not None:
            raise ValueError('The parameters endid and endtime may not be set '
                             'at the same time.')
        if isinstance(starttime, basestring):
            starttime = pywikibot.Timestamp.fromtimestampformat(starttime)
        if isinstance(endtime, basestring):
            endtime = pywikibot.Timestamp.fromtimestampformat(endtime)
        # required comparisons: X <= endid, and Y < endid/endtime; check_after
        # only supports <, but as == works in both directions, the <= can be
        # split in check_after() and ==, check_after also checks that the end*
        # value is not False (via not); check_after basically checks, if there
        # the end is after (further along a theoretical queue) the current
        if reverse:
            check_after = _RevisionCache._is_smaller
        else:
            check_after = _RevisionCache._is_bigger
        if (isinstance(assume_newest, datetime.datetime) and
                assume_newest < self._latest_revision_requested):
            assume_newest = True
        if starttime is not None:
            if check_after(endtime, starttime):
                raise ValueError('starttime must be before the endtime')
            chunk_index = self.bisect_right(self._cache, starttime,
                                            key=lambda chunk: chunk[-1].timestamp, reverse=True)
            if (chunk_index < len(self._cache) and
                    self._cache[chunk_index][0].timestamp > starttime):
                if reverse:
                    idx = self.bisect_right(self._cache[chunk_index], starttime,
                                            key=self._key_time, reverse=True)
                else:
                    idx = self.bisect_left(self._cache[chunk_index], starttime,
                                           key=self._key_time, reverse=True)
                starttime = None  # found cache, continue using id
            else:
                idx = False
        elif startid is not None:
            # TODO: Determine when startid is after endid
            #    raise ValueError('startid must be before the endid.')
            chunk_index, idx = self._index(startid)
            if chunk_index is False:
                for chunk_index, chunk in enumerate(self._cache):
                    if chunk[0].revid < startid:
                        break
                else:
                    chunk_index = len(self._cache)
                idx = -1
            # the chunk_index is the position in the cache before which the list
            # is going to be added
            if chunk_index >= len(self._cache):
                pass  # print('startid after cache')  # add to the end
            elif idx < 0:
                pass  # print('startid between chunks {0}'.format(chunk_index))
            else:
                # starts inside of the cache
                # print('startid entry #{0}C{1} id {2}'.format(chunk_index, idx, self._cache[chunk_index][idx].revid))
                assert(self._cache[chunk_index][idx].revid == startid)
        elif reverse and self._cache and self._cache[-1][-1].parent_id == 0:
            # if startid is None, the startid is defined in reverse mode, when
            # the last entry is really the last entry (meaning parent_id == 0)
            startid = self._cache[-1][-1].revid
            chunk_index = len(self._cache) - 1
            idx = len(self._cache[-1]) - 1
        else:
            if reverse:
                chunk_index = len(self._cache)
            else:
                chunk_index = 0
            if assume_newest and self._cache:
                if reverse:
                    if not endid:
                        endid = self._cache[0][0].revid
                    idx = False
                else:
                    idx = 0
            else:
                idx = False
        first_request = True
        while total is None or total > 0:
            if idx is not False and idx >= 0:
                # It starts by returning cached items
                if reverse:
                    cached_block = self._cache[chunk_index][idx::-1]
                else:
                    cached_block = self._cache[chunk_index][idx:]
                # print('Idx: {0} ID: {1}'.format(idx, ','.join(str(_.revid) for _ in cached_block)))
                cached_block, stopped = self._get_cached(cached_block, endid, endtime, total, check_after)
                for cached in self._fill_cached(cached_block, content, rollback):
                    # print('yield C {0}'.format(cached.revid))
                    yield cached
                if stopped:
                    return
                if not reverse:
                    # add after current, when not in reverse mode
                    chunk_index += 1
                if total is not None:
                    total -= len(cached_block)
            else:
                # Does not continue cache, so doesn't start from the last cached
                if chunk_index is False:
                    chunk_index = 0
            # There were cached entries returned before the first request
            # then the next request is going from the last cached entry
            if reverse and 0 <= chunk_index < len(self._cache):
                # unfortunately we can't use the new item
                last_cached_id = self._cache[chunk_index][0].revid
            elif not reverse and 0 < chunk_index <= len(self._cache):
                last_cached_id = self._cache[chunk_index - 1][-1].parent_id
            else:
                last_cached_id = False
            gen = pywikibot.data.api.PropertyGenerator(
                prop='revisions', rvdir='newer' if reverse else 'older',
                site=self._page.site, titles=self._page.title())
            if content:
                gen.request['rvprop'] = ('ids|flags|timestamp|'
                                         'user|comment|content')
            if rollback and self._page.site.version() < MediaWikiVersion('1.24wmf19'):
                gen.request['rvtoken'] = 'rollback'
            # get newest revid
            if reverse and chunk_index > 1:
                next_cached = self._cache[chunk_index - 1][-1]
            elif not reverse and len(self._cache) > chunk_index:
                next_cached = self._cache[chunk_index][0]
            else:
                next_cached = None
            if next_cached:
                if check_after(endtime, next_cached.timestamp):
                    next_cached_id = False
                    gen.request['rvendtime'] = endtime
                elif check_after(endid, next_cached.revid):
                    next_cached_id = False
                    gen.request['rvendid'] = endid
                else:
                    next_cached_id = next_cached.revid
                    gen.request['rvendid'] = next_cached_id
            else:
                next_cached_id = False
                gen.request['rvendid'] = False if not endid else endid
                gen.request['rvendtime'] = False if not endtime else endtime
            if reverse:
                requesting_latest = not endid and not endtime
            else:
                requesting_latest = not startid and not starttime
            if last_cached_id:
                gen.request['rvstartid'] = last_cached_id
            if starttime:
                gen.request['rvstarttime'] = starttime
                starttime = None  # this is not going to be used anymore
            if total:
                if last_cached_id in self:
                    # that includes the first cached entry, so query one more
                    gen.set_maximum_items(total + 1)
                else:
                    gen.set_maximum_items(total)
            # print('R {0} to {1} Total: {2}, L/NCID: {3}, {4}'.format(
            #       '-----' if 'rvstartid' not in gen.request else gen.request['rvstartid'][0],
            #       '-----' if 'rvendid' not in gen.request else gen.request['rvendid'][0],
            #       total, last_cached_id, next_cached_id))
            for pagedata in gen:
                if not self._page.site.sametitle(
                        pagedata['title'],
                        self._page.title(withSection=False)):
                    raise pywikibot.Error(
                        u"get_revisions: Query on %s returned data on '%s'"
                        % (self._page, pagedata['title']))
                if requesting_latest and not reverse:
                    self._latest_revision_requested = datetime.datetime.utcnow()
                    requesting_latest = False
                if 'revisions' not in pagedata:
                    # the chosen ID for the first cached revision was before
                    # the start id.
                    assert(first_request)  # no revisions should have been added
                    if reverse:
                        chunk_index -= 1
                    else:
                        chunk_index += 1
                    first_request = False
                    continue
                first_request = False
                chunk = self.cache_revisions(pagedata['revisions'])
                chains = self._rev_chains(chunk)
                # print('Chunk: {0} in Chains: {1}'.format([_.revid for _ in chunk], [[_.revid for _ in c] for c in chains]))
                if last_cached_id is not False:
                    # If the request didn't returned the last cached ID then
                    # this is probably because the API doesn't return the revs
                    # in a sane manner. See also T91883
                    for chain in chains:
                        start = self._revid_index(chain, last_cached_id)
                        if start >= 0:
                            # don't yield start in reverse
                            if reverse:
                                start -= 1
                            break
                    else:
                        pywikibot.log('Start revision not in result.')
                        start = False
                else:
                    if reverse:
                        chain = min(chains, key=lambda chain: chain[-1].timestamp)
                    else:
                        chain = max(chains, key=lambda chain: chain[0].timestamp)
                    if reverse and startid is None and chain[0].parent_id != 0:
                        # When last_cached_id is False, it should contain the
                        # first revision in reverse mode
                        pywikibot.log('Response did not contain first revision.')
                        start = False
                    else:
                        start = 0
                if start is False:
                    # The API hasn't started with a valid revision. There is no
                    # sane way in recovering it with the least impact. Instead
                    # just cache all revisions and hope that the API won't screw
                    # up there. Berserk mode basically.
                    print('START FAILURE')
                    self.cache_revisions(list(self._revision_generator()))
                    assert(len(self._cache) == 1)
                    chain = self._cache[0]
                    chunk_index = 0
                    if last_cached_id is not False:
                        start = self._revid_index(chain, last_cached_id)
                        assert(start >= 0)
                    else:
                        start = len(chain) - 1 if reverse else 0
                if start >= 0:
                    if reverse:
                        chain = chain[start::-1]
                    else:
                        chain = chain[start:]
                    end = self._revid_index(chain, next_cached_id)
                    if end >= 0:
                        chain = chain[:end + 1]
                    chain, stopped = self._get_cached(chain, endid, endtime, total, check_after)
                    # print('Chain (truncated): {0}'.format([_.revid for _ in chain]))
                    for rev in chain:
                        # print('yield R {0}'.format(rev.revid))
                        yield rev
                    if total is not None:
                        total -= len(chain)
                    if stopped:
                        break
                    chunk_index, idx = self._index(chain[-1].revid)
                    # print(idx)
                    assert(chunk_index is not False)
                    assert(idx is not False)
                    if reverse and idx > 0:
                        # not at the start of the chunk, so could yield cached
                        idx -= 1
                        break
                    elif not reverse and idx < len(self._cache[chunk_index]) - 1:
                        # not at the end of the chunk, so could yield cached
                        idx += 1
                        break
            else:
                # last id was not found in the cache, so continue requesting
                idx = False
                if reverse:
                    chunk_index -= 1
                else:
                    chunk_index += 1
            if requesting_latest and reverse:
                self._latest_revision_requested = datetime.datetime.utcnow()


class FileInfo(DotReadableDict):

    """
    A structure holding imageinfo of latest rev. of FilePage.

    All keys of API imageinfo dictionary are mapped to FileInfo attributes.
    Attributes can be retrieved both as self['key'] or self.key.

    Following attributes will be returned:
        - timestamp, user, comment, url, size, sha1, mime, metadata
        - archivename (not for latest revision)

    See Site.loadimageinfo() for details.

    Note: timestamp will be casted to pywikibot.Timestamp.
    """

    def __init__(self, file_revision):
        """
        Create class with the dictionary returned by site.loadimageinfo().

        @param page: FilePage containing the image.
        @type page: FilePage object
        """
        self.__dict__.update(file_revision)
        self.timestamp = pywikibot.Timestamp.fromISOformat(self.timestamp)

    def __eq__(self, other):
        """Test if two File_info objects are equal."""
        return self.__dict__ == other.__dict__


class Link(ComparableMixin):

    """
    A MediaWiki link (local or interwiki).

    Has the following attributes:

      - site: The Site object for the wiki linked to
      - namespace: The namespace of the page linked to (int)
      - title: The title of the page linked to (unicode); does not include
        namespace or section
      - section: The section of the page linked to (unicode or None); this
        contains any text following a '#' character in the title
      - anchor: The anchor text (unicode or None); this contains any text
        following a '|' character inside the link

    """

    illegal_titles_pattern = re.compile(
        # Matching titles will be held as illegal.
        r'''[\x00-\x1f\x23\x3c\x3e\x5b\x5d\x7b\x7c\x7d\x7f]'''
        # URL percent encoding sequences interfere with the ability
        # to round-trip titles -- you can't link to them consistently.
        u'|%[0-9A-Fa-f]{2}'
        # XML/HTML character references produce similar issues.
        u'|&[A-Za-z0-9\x80-\xff]+;'
        u'|&#[0-9]+;'
        u'|&#x[0-9A-Fa-f]+;'
    )

    def __init__(self, text, source=None, defaultNamespace=0):
        """
        Constructor.

        @param text: the link text (everything appearing between [[ and ]]
            on a wiki page)
        @type text: unicode
        @param source: the Site on which the link was found (not necessarily
            the site to which the link refers)
        @type source: Site or BasePage
        @param defaultNamespace: a namespace to use if the link does not
            contain one (defaults to 0)
        @type defaultNamespace: int

        @raises UnicodeError: text could not be converted to unicode.
            On Python 2.6.6 without unicodedata2, this could also be raised
            if the text contains combining characters.
            See https://phabricator.wikimedia.org/T102461
        """
        source_is_page = isinstance(source, BasePage)

        assert source is None or source_is_page or isinstance(source, pywikibot.site.BaseSite), \
            "source parameter should be either a Site or Page object"

        if source_is_page:
            self._source = source.site
        else:
            self._source = source or pywikibot.Site()

        self._text = text
        # See bug T104864, defaultNamespace might have been deleted.
        try:
            self._defaultns = self._source.namespaces[defaultNamespace]
        except KeyError:
            self._defaultns = defaultNamespace

        # preprocess text (these changes aren't site-dependent)
        # First remove anchor, which is stored unchanged, if there is one
        if u"|" in self._text:
            self._text, self._anchor = self._text.split(u"|", 1)
        else:
            self._anchor = None

        # Convert URL-encoded characters to unicode
        encodings = [self._source.encoding()] + list(self._source.encodings())

        self._text = url2unicode(self._text, encodings=encodings)

        # Clean up the name, it can come from anywhere.
        # Convert HTML entities to unicode
        t = html2unicode(self._text)

        # Normalize unicode string to a NFC (composed) format to allow
        # proper string comparisons to strings output from MediaWiki API.
        # Due to Python issue 10254, this is not possible on Python 2.6.6
        # if the string contains combining characters. See T102461.
        if (PYTHON_VERSION == (2, 6, 6) and
                unicodedata.__name__ != 'unicodedata2' and
                any(unicodedata.combining(c) for c in t)):
            raise UnicodeError(
                'Link(%r, %s): combining characters detected, which are '
                'not supported by Pywikibot on Python 2.6.6. See '
                'https://phabricator.wikimedia.org/T102461'
                % (t, self._source))
        t = unicodedata.normalize('NFC', t)

        # This code was adapted from Title.php : secureAndSplit()
        #
        if u'\ufffd' in t:
            raise pywikibot.Error(
                "Title contains illegal char (\\uFFFD 'REPLACEMENT CHARACTER')")

        # Cleanup whitespace
        t = re.sub(
            '[_ \xa0\u1680\u180E\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+',
            ' ', t)
        # Strip spaces at both ends
        t = t.strip()
        # Remove left-to-right and right-to-left markers.
        t = t.replace(u"\u200e", u"").replace(u"\u200f", u"")
        self._text = t

        if source_is_page:
            self._text = source.title(withSection=False) + self._text

    def __repr__(self):
        """Return a more complete string representation."""
        return "pywikibot.page.Link(%r, %r)" % (self.title, self.site)

    def parse_site(self):
        """
        Parse only enough text to determine which site the link points to.

        This method does not parse anything after the first ":"; links
        with multiple interwiki prefixes (such as "wikt:fr:Parlais") need
        to be re-parsed on the first linked wiki to get the actual site.

        @return: The family name and site code for the linked site. If the site
            is not supported by the configured families it returns None instead
            of a str.
        @rtype: tuple
        """
        t = self._text
        fam = self._source.family
        code = self._source.code
        while u":" in t:
            # Initial colon
            if t.startswith(u":"):
                # remove the colon but continue processing
                # remove any subsequent whitespace
                t = t.lstrip(u":").lstrip(u" ")
                continue
            prefix = t[:t.index(u":")].lower()  # part of text before :
            ns = self._source.namespaces.lookup_name(prefix)
            if ns:
                # The prefix is a namespace in the source wiki
                return (fam.name, code)
            if prefix in fam.langs:
                # prefix is a language code within the source wiki family
                return (fam.name, prefix)
            try:
                newsite = self._source.interwiki(prefix)
            except KeyError:
                break  # text before : doesn't match any known prefix
            except SiteDefinitionError:
                return (None, None)
            else:
                return (newsite.family.name, newsite.code)
        return (fam.name, code)  # text before : doesn't match any known prefix

    def parse(self):
        """
        Parse wikitext of the link.

        Called internally when accessing attributes.
        """
        self._site = self._source
        self._namespace = self._defaultns
        self._is_interwiki = False
        t = self._text
        ns_prefix = False

        # This code was adapted from Title.php : secureAndSplit()
        #
        first_other_site = None
        while u":" in t:
            # Initial colon indicates main namespace rather than default
            if t.startswith(u":"):
                self._namespace = self._site.namespaces[0]
                # remove the colon but continue processing
                # remove any subsequent whitespace
                t = t.lstrip(u":").lstrip(u" ")
                continue

            prefix = t[:t.index(u":")].lower()
            ns = self._site.namespaces.lookup_name(prefix)
            if ns:
                # Ordinary namespace
                t = t[t.index(u":"):].lstrip(u":").lstrip(u" ")
                self._namespace = ns
                ns_prefix = True
                break
            try:
                newsite = self._site.interwiki(prefix)
            except KeyError:
                break  # text before : doesn't match any known prefix
            except SiteDefinitionError as e:
                raise SiteDefinitionError(
                    u'{0} is not a local page on {1}, and the interwiki prefix '
                    '{2} is not supported by Pywikibot!:\n{3}'.format(
                        self._text, self._site, prefix, e))
            else:
                t = t[t.index(u":"):].lstrip(u":").lstrip(u" ")
                if first_other_site:
                    if not self._site.local_interwiki(prefix):
                        raise pywikibot.InvalidTitle(
                            u'{0} links to a non local site {1} via an '
                            'interwiki link to {2}.'.format(
                                self._text, newsite, first_other_site))
                elif newsite != self._source:
                    first_other_site = newsite
                self._site = newsite
                self._is_interwiki = True

        if u"#" in t:
            t, sec = t.split(u'#', 1)
            t, self._section = t.rstrip(), sec.lstrip()
        else:
            self._section = None

        if ns_prefix:
            # 'namespace:' is not a valid title
            if not t:
                raise pywikibot.InvalidTitle(
                    u"'{0}' has no title.".format(self._text))
            elif ':' in t and self._namespace >= 0:  # < 0 don't have talk
                other_ns = self._site.namespaces[self._namespace - 1
                                                 if self._namespace % 2 else
                                                 self._namespace + 1]
                if '' in other_ns:  # other namespace uses empty str as ns
                    next_ns = t[:t.index(':')]
                    if self._site.namespaces.lookup_name(next_ns):
                        raise pywikibot.InvalidTitle(
                            u"The (non-)talk page of '{0}' is a valid title "
                            "in another namespace.".format(self._text))

        # Reject illegal characters.
        m = Link.illegal_titles_pattern.search(t)
        if m:
            raise pywikibot.InvalidTitle(
                u"%s contains illegal char(s) %s" % (repr(t), repr(m.group(0))))

        # Pages with "/./" or "/../" appearing in the URLs will
        # often be unreachable due to the way web browsers deal
        # * with 'relative' URLs. Forbid them explicitly.

        if u'.' in t and (
                t == u'.' or t == u'..' or
                t.startswith(u'./') or
                t.startswith(u'../') or
                u'/./' in t or
                u'/../' in t or
                t.endswith(u'/.') or
                t.endswith(u'/..')
        ):
            raise pywikibot.InvalidTitle(
                u"(contains . / combinations): '%s'"
                % self._text)

        # Magic tilde sequences? Nu-uh!
        if u"~~~" in t:
            raise pywikibot.InvalidTitle(u"(contains ~~~): '%s'" % self._text)

        if self._namespace != -1 and len(t) > 255:
            raise pywikibot.InvalidTitle(u"(over 255 bytes): '%s'" % t)

        # "empty" local links can only be self-links
        # with a fragment identifier.
        if not t.strip() and not self._is_interwiki:
            raise pywikibot.InvalidTitle("The link does not contain a page "
                                         "title")

        if self._site.namespaces[self._namespace].case == 'first-letter':
            t = first_upper(t)

        self._title = t

    # define attributes, to be evaluated lazily

    @property
    def site(self):
        """
        Return the site of the link.

        @rtype: unicode
        """
        if not hasattr(self, "_site"):
            self.parse()
        return self._site

    @property
    def namespace(self):
        """
        Return the namespace of the link.

        @rtype: unicode
        """
        if not hasattr(self, "_namespace"):
            self.parse()
        return self._namespace

    @property
    def title(self):
        """
        Return the title of the link.

        @rtype: unicode
        """
        if not hasattr(self, "_title"):
            self.parse()
        return self._title

    @property
    def section(self):
        """
        Return the section of the link.

        @rtype: unicode
        """
        if not hasattr(self, "_section"):
            self.parse()
        return self._section

    @property
    def anchor(self):
        """
        Return the anchor of the link.

        @rtype: unicode
        """
        if not hasattr(self, "_anchor"):
            self.parse()
        return self._anchor

    def canonical_title(self):
        """Return full page title, including localized namespace."""
        # Avoid that ':' will be added to the title for Main ns.
        if self.namespace != Namespace.MAIN:
            return "%s:%s" % (self.site.namespace(self.namespace),
                              self.title)
        else:
            return self.title

    def ns_title(self, onsite=None):
        """
        Return full page title, including namespace.

        @param onsite: site object
            if specified, present title using onsite local namespace,
            otherwise use self canonical namespace.

        @raise pywikibot.Error: no corresponding namespace is found in onsite
        """
        if onsite is None:
            name = self.namespace.canonical_name
        else:
            # look for corresponding ns in onsite by name comparison
            for alias in self.namespace:
                namespace = onsite.namespaces.lookup_name(alias)
                if namespace is not None:
                    name = namespace.custom_name
                    break
            else:
                # not found
                raise pywikibot.Error(
                    u'No corresponding namespace found for namespace %s on %s.'
                    % (self.namespace, onsite))

        if self.namespace != Namespace.MAIN:
            return u'%s:%s' % (name, self.title)
        else:
            return self.title

    def astext(self, onsite=None):
        """
        Return a text representation of the link.

        @param onsite: if specified, present as a (possibly interwiki) link
            from the given site; otherwise, present as an internal link on
            the source site.
        """
        if onsite is None:
            onsite = self._source
        title = self.title
        if self.namespace != Namespace.MAIN:
            title = onsite.namespace(self.namespace) + ":" + title
        if self.section:
            title = title + "#" + self.section
        if onsite == self.site:
            return u'[[%s]]' % title
        if onsite.family == self.site.family:
            return u'[[%s:%s]]' % (self.site.code, title)
        if self.site.family.name == self.site.code:
            # use this form for sites like commons, where the
            # code is the same as the family name
            return u'[[%s:%s]]' % (self.site.code,
                                   title)
        return u'[[%s:%s:%s]]' % (self.site.family.name,
                                  self.site.code,
                                  title)

    if sys.version_info[0] > 2:
        def __str__(self):
            """Return a string representation."""
            return self.__unicode__()
    else:
        def __str__(self):
            """Return a string representation."""
            return self.astext().encode("ascii", "backslashreplace")

    def _cmpkey(self):
        """
        Key for comparison of Link objects.

        Link objects are "equal" if and only if they are on the same site
        and have the same normalized title, including section if any.

        Link objects are sortable by site, then namespace, then title.
        """
        return (self.site, self.namespace, self.title)

    def __unicode__(self):
        """
        Return a unicode string representation.

        @rtype: unicode
        """
        return self.astext()

    def __hash__(self):
        """A stable identifier to be used as a key in hash-tables."""
        return hash(u'%s:%s:%s' % (self.site.family.name,
                                   self.site.code,
                                   self.title))

    @classmethod
    def fromPage(cls, page, source=None):
        """
        Create a Link to a Page.

        @param page: target Page
        @type page: Page
        @param source: Link from site source
        @param source: Site

        @rtype: Link
        """
        link = cls.__new__(cls)
        link._site = page.site
        link._section = page.section()
        link._namespace = page.namespace()
        link._title = page.title(withNamespace=False,
                                 allowInterwiki=False,
                                 withSection=False)
        link._anchor = None
        link._source = source or pywikibot.Site()

        return link

    @classmethod
    def langlinkUnsafe(cls, lang, title, source):
        """
        Create a "lang:title" Link linked from source.

        Assumes that the lang & title come clean, no checks are made.

        @param lang: target site code (language)
        @type lang: str
        @param title: target Page
        @type title: unicode
        @param source: Link from site source
        @param source: Site

        @rtype: Link
        """
        link = cls.__new__(cls)
        if source.family.interwiki_forward:
            link._site = pywikibot.Site(lang, source.family.interwiki_forward)
        else:
            link._site = pywikibot.Site(lang, source.family.name)
        link._section = None
        link._source = source

        link._namespace = 0

        if ':' in title:
            ns, t = title.split(':', 1)
            ns = link._site.namespaces.lookup_name(ns)
            if ns:
                link._namespace = ns
                title = t
        if u"#" in title:
            t, sec = title.split(u'#', 1)
            title, link._section = t.rstrip(), sec.lstrip()
        else:
            link._section = None
        link._title = title
        return link

    @classmethod
    def create_separated(cls, link, source, default_namespace=0, section=None,
                         label=None):
        """
        Create a new instance but overwrite section or label.

        The returned Link instance is already parsed.

        @param link: The original link text.
        @type link: str
        @param source: The source of the link.
        @type source: Site
        @param default_namespace: The namespace this link uses when no namespace
            is defined in the link text.
        @type default_namespace: int
        @param section: The new section replacing the one in link. If None
            (default) it doesn't replace it.
        @type section: None or str
        @param label: The new label replacing the one in link. If None (default)
            it doesn't replace it.
        """
        link = cls(link, source, default_namespace)
        link.parse()
        if section:
            link._section = section
        elif section is not None:
            link._section = None
        if label:
            link._anchor = label
        elif label is not None:
            link._anchor = ''
        return link


# Utility functions for parsing page titles


def html2unicode(text, ignore=None):
    """
    Replace HTML entities with equivalent unicode.

    @param ignore: HTML entities to ignore
    @param ignore: list of int

    @rtype: unicode
    """
    if ignore is None:
        ignore = []
    # This regular expression will match any decimal and hexadecimal entity and
    # also entities that might be named entities.
    entityR = re.compile(
        r'&(#(?P<decimal>\d+)|#x(?P<hex>[0-9a-fA-F]+)|(?P<name>[A-Za-z]+));')
    # These characters are Html-illegal, but sadly you *can* find some of
    # these and converting them to chr(decimal) is unsuitable
    convertIllegalHtmlEntities = {
        128: 8364,  # €
        130: 8218,  # ‚
        131: 402,   # ƒ
        132: 8222,  # „
        133: 8230,  # …
        134: 8224,  # †
        135: 8225,  # ‡
        136: 710,   # ˆ
        137: 8240,  # ‰
        138: 352,   # Š
        139: 8249,  # ‹
        140: 338,   # Œ
        142: 381,   # Ž
        145: 8216,  # ‘
        146: 8217,  # ’
        147: 8220,  # “
        148: 8221,  # ”
        149: 8226,  # •
        150: 8211,  # –
        151: 8212,  # —
        152: 732,   # ˜
        153: 8482,  # ™
        154: 353,   # š
        155: 8250,  # ›
        156: 339,   # œ
        158: 382,   # ž
        159: 376    # Ÿ
    }
    # ensuring that illegal &#129; &#141; and &#157, which have no known values,
    # don't get converted to chr(129), chr(141) or chr(157)
    ignore = (set(map(lambda x: convertIllegalHtmlEntities.get(x, x), ignore)) |
              set([129, 141, 157]))

    def handle_entity(match):
        if match.group('decimal'):
            unicodeCodepoint = int(match.group('decimal'))
        elif match.group('hex'):
            unicodeCodepoint = int(match.group('hex'), 16)
        elif match.group('name'):
            name = match.group('name')
            if name in htmlentitydefs.name2codepoint:
                # We found a known HTML entity.
                unicodeCodepoint = htmlentitydefs.name2codepoint[name]
            else:
                unicodeCodepoint = False

        if unicodeCodepoint in convertIllegalHtmlEntities:
            unicodeCodepoint = convertIllegalHtmlEntities[unicodeCodepoint]

        if unicodeCodepoint and unicodeCodepoint not in ignore:
            if unicodeCodepoint > sys.maxunicode:
                # solve narrow Python 2 build exception (UTF-16)
                return eval("'\\U{0:08x}'".format(unicodeCodepoint))
            else:
                return chr(unicodeCodepoint)
        else:
            # Leave the entity unchanged
            return match.group(0)
    return entityR.sub(handle_entity, text)


def UnicodeToAsciiHtml(s):
    """Convert unicode to a str using HTML entities."""
    html = []
    for c in s:
        cord = ord(c)
        if 31 < cord < 128:
            html.append(c)
        else:
            html.append('&#%d;' % cord)
    return ''.join(html)


def unicode2html(x, encoding):
    """
    Convert unicode string to requested HTML encoding.

    Attempt to encode the
    string into the desired format; if that doesn't work, encode the unicode
    into HTML &#; entities. If it does work, return it unchanged.

    @param x: String to update
    @type x: unicode
    @param encoding: Encoding to use
    @type encoding: str

    @rtype: str
    """
    try:
        x.encode(encoding)
    except UnicodeError:
        x = UnicodeToAsciiHtml(x)
    return x


@deprecated_args(site2=None, site='encodings')
def url2unicode(title, encodings='utf-8'):
    """
    Convert URL-encoded text to unicode using several encoding.

    Uses the first encoding that doesn't cause an error.

    @param title: URL-encoded character data to convert
    @type title: str
    @param encodings: Encodings to attempt to use during conversion.
    @type encodings: str, list or Site
    @rtype: unicode

    @raise UnicodeError: Could not convert using any encoding.
    """
    if isinstance(encodings, basestring):
        encodings = [encodings]
    elif isinstance(encodings, pywikibot.site.BaseSite):
        # create a list of all possible encodings for both hint sites
        site = encodings
        encodings = [site.encoding()] + list(site.encodings())

    firstException = None
    for enc in encodings:
        try:
            t = title.encode(enc)
            t = unquote_to_bytes(t)
            return t.decode(enc)
        except UnicodeError as ex:
            if not firstException:
                firstException = ex
            pass
    # Couldn't convert, raise the original exception
    raise firstException
