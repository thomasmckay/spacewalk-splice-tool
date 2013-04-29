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
import os
import pprint
import subprocess
import sys
import StringIO
import csv
import traceback
from optparse import OptionParser

from spacewalk_splice_tool import facts
from cpin_connect import CandlepinConnection

class SpacewalkClient(object):
    
    def get_db_output(self, report_path):
        # capture data from spacewalk
        process = subprocess.Popen(
                    ['/usr/bin/ssh', '-i', os.environ['SPACEWALK_SSH_KEY'],
                     os.environ['SPACEWALK_HOST'],
                     '/usr/bin/spacewalk-report', report_path], 
                    stdout=subprocess.PIPE)
        stdout, stderr = process.communicate()

        reader = csv.DictReader(stdout.decode('ascii').splitlines())

        #XXX: suboptimal 
        retval = []
        for r in reader:
            retval.append(r)

        #retval = [
        #    '1000010000,Red Hat (Internal Use Only),1,beav-sat-client,beav-sat-client,10.16.79.126,,beav,2013-04-17 20:05:34,2013-04-18 08:08:10,rhel-x86_64-server-6,Spacewalk Management Entitled Servers,,,x86_64,1 CPUs 1 Sockets; eth0 10.16.79.126/255.255.252.0 52:54:00:26:96:a7; lo 127.0.0.1/255.0.0.0 00:00:00:00:00:00,996,1'
        #    ]

        return retval

    def get_system_list(self):
        return self.get_db_output('cp-export')

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
