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
import xmlrpclib
from optparse import OptionParser

from spacewalk_splice_tool import facts
from cpin_connect import CandlepinConnection

class SpacewalkClient(object):
    
    def get_db_output(self, report_path):
        # capture data from spacewalk
        process = subprocess.Popen(['/usr/bin/spacewalk-report', report_path], stdout=subprocess.PIPE)
        stdout, stderr = process.communicate()

        reader = csv.DictReader(stdout.decode('ascii').splitlines())

        #XXX: suboptimal 
        retval = []
        for r in reader:
            retval.append(r)

        return retval

    def get_system_list(self):
        return self.get_db_output('cp-export')

    def get_org_list(self):
        # we grab the full user list and then extract the orgs. This is not as
        # efficient as just getting the orgs from the db, but we may want to
        # create person consumers in the future.
        full_user_list = self.get_db_output('users')
        orgs = {}
        for u in full_user_list:
            orgs[u['organization_id']] = u['organization']

        return orgs


    def get_clone_origin_channel(self, channel_label):
        # this returns the "root" channel that the given channel was cloned from,
        # or the name of the channel itself if the "root" was passed in to begin with
        original_channel = self.connection.channel.software.getDetails(self.key, channel_label)['clone_original']
        if original_channel:
            return self.get_clone_origin_channel(original_channel)
        return channel_label

    def get_channel_list(self):
        channel_list = self.connection.channel.listSoftwareChannels(self.key)
        return map(lambda x: x['label'], channel_list)

    def set_candlepin_uuid(self, sid, uuid):
        if self.get_candlepin_uuid(sid):
            raise Exception("candlepin_uuid already exists on %s!"  % sid)
        self.connection.system.addNote(self.key, sid, 'candlepin_uuid', uuid)


def transform_and_post_consumer(system, cpin_conn):
    cpin_conn.createConsumer(name=system['name'], facts=facts.translate_sw_facts_to_subsmgr(system), installed_products=None) 
    return system
