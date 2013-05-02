# -*- coding: utf-8 -*-
#
# Copyright © 2014 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.


import unittest

import mock

from spacewalk_splice_tool import utils


class SpliceToolTest(unittest.TestCase):

    def setUp(self):
        super(SpliceToolTest, self).setUp()
        self.mock_get_release()

    def tearDown(self):
        super(SpliceToolTest, self).tearDown()
        self.unmock_get_release()

    def mock_get_release(self):
        self.old_get_release = utils.getRelease
        utils.getRelease = mock.Mock(return_value="RHEL-6.4")

    def unmock_get_release(self):
        utils.getRelease = self.old_get_release
