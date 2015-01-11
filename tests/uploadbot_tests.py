# -*- coding: utf-8  -*-
"""
UploadRobot test.

These tests write to the wiki.
"""
#
# (C) Pywikibot team, 2015
#
# Distributed under the terms of the MIT license.
#
__version__ = '$Id$'
#

import os
import time

import pywikibot
from scripts import upload
from tests import _images_dir
from tests.aspects import unittest, TestCase


class TestUploadbot(TestCase):

    """Test cases for upload."""

    write = True

    family = 'wikipedia'
    code = 'test'

    def test_png_list_with_file_pages(self):
        """Test uploading a list of pngs with unique descriptions using upload.py."""
        file_urls = []
        for directory_info in os.walk(_images_dir):
            for dir_file in directory_info[2]:
                file_urls.append(os.path.join(directory_info[0], dir_file))
        file_datas = []
        description = ("pywikibot upload.py script test. "
                       "Tested uploading a list of pngs with specified list "
                       "of FilePage objects. File number is ")
        counter = 1
        for file_url in file_urls:
            filename = make_unique_filename(file_url)
            file_page = pywikibot.FilePage(self.get_site(), filename)
            file_page.text = description + str(counter)
            file_datas.append((file_url, file_page))
            # make description suffix unique
            counter += 1
        bot = upload.UploadRobot(url=file_datas,
                                 description="Is used if not FilePage.text",
                                 useFilename=None, keepFilename=True,
                                 verifyDescription=False, aborts=set(),
                                 ignoreWarning=True, targetSite=self.get_site())
        bot.run()

    def test_png(self):
        """Test uploading a png using upload.py."""
        path = os.path.join(_images_dir, "MP_sounds.png")
        filename = make_unique_filename(path)
        bot = upload.UploadRobot(url=[(path, None)],
                                 description="pywikibot upload.py script test. "
                                 "Tested uploading a png.",
                                 useFilename=filename, keepFilename=True,
                                 verifyDescription=False, aborts=set(),
                                 ignoreWarning=True, targetSite=self.get_site())
        bot.run()

    def test_png_url(self):
        """Test uploading a png from url using upload.py."""
        path = 'https://upload.wikimedia.org/wikipedia/commons/f/fc/MP_sounds.png'
        filename = make_unique_filename(path)
        bot = upload.UploadRobot(url=[(path, None)],
                                 description="pywikibot upload.py script test. "
                                 "Tested uploading a png from url.",
                                 useFilename=filename, keepFilename=True,
                                 verifyDescription=False, aborts=set(),
                                 ignoreWarning=True, targetSite=self.get_site())
        bot.run()


def make_unique_filename(path):
    """Make unique filename to run test without human attention required."""
    base = os.path.basename(path)
    file_path = os.path.splitext(base)[0]
    file_extension = os.path.splitext(base)[1]
    filename = file_path + ' ' + str(time.time()) + file_extension
    return filename

if __name__ == '__main__':
    try:
        unittest.main()
    except SystemExit:
        pass
