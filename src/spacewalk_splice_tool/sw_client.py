#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright © 2012 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.

from datetime import datetime
from dateutil.tz import tzutc
import pprint
import subprocess
import sys
import StringIO
import csv
import traceback
from optparse import OptionParser

from spacewalk_splice_tool import facts


class SpacewalkClient(object):
    
    def __init__(self, host, ssh_key_path):
        self.host = host
        self.ssh_key_path = ssh_key_path

    def get_db_output(self, report_path):
        # capture data from spacewalk
        process = subprocess.Popen(
                    ['/usr/bin/ssh', '-i', self.ssh_key_path,
                     self.host, '/usr/bin/spacewalk-report', report_path], 
                    stdout=subprocess.PIPE)
        stdout, stderr = process.communicate()

        reader = csv.DictReader(stdout.decode('ascii').splitlines())

        #XXX: suboptimal 
        retval = []
        for r in reader:
            retval.append(r)

        return retval

    def get_system_list(self):
        return self.get_db_output('splice-export')

    def get_host_guest_list(self):
        return self.get_db_output('hostguests')

    def get_channel_list(self):
        return self.get_db_output('cloned-channels')

    def get_org_list(self):
        # we grab the full user list and then extract the orgs. This is not as
        # efficient as just getting the orgs from the db, but we may want to
        # create person consumers in the future.
        full_user_list = self.get_db_output('users')
        orgs = {}
        for u in full_user_list:
            orgs[u['organization_id']] = u['organization']

        return orgs

    def get_user_list(self):
        users = self.get_db_output('users')
        return users
