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
import sys
import traceback
import xmlrpclib
from optparse import OptionParser

from spacewalk_splice_tool import facts

class SpacewalkClient(object):
    
    def __init__(self, hostname, username, password, handler="/rpc/api"):
        self.username = username
        self.password = password
        self.connection = xmlrpclib.Server("https://" + hostname + handler, verbose=0)
        self.key = self.login()

    def login(self):
        """
         login to xmlrpc server and grab authentication credentials
        """
        return self.connection.auth.login(self.username, self.password)

    def logout(self):
        """
         log out of the xmlrpc session
        """
        self.connection.auth.logout(self.key)
    
    def get_active_systems(self, system_group=None):
        """
         get list of all active systems
        """
        if system_group:
            systemids = self.connection.systemgroup.listActiveSystemsInGroup(self.key, system_group)
        else:
            # grab all active systems
            active_system_list = self.connection.system.listActiveSystems(self.key)
            systemids = [info['id'] for info in active_system_list]
        return systemids

    def get_active_systems_details(self, active_system_ids):
        """
         get system details for all active system ids
        """
        system_details = self.connection.system.listActiveSystemsDetails(self.key, active_system_ids)
        return system_details

    def get_inactive_systems(self, system_group=None):
        """
         get list of all inactive systems
        """
        if system_group:
            systemids = self.connection.systemgroup.listInactiveSystemsInGroup(self.key, system_group)
        else:
            # grab all inactive systems
            inactive_system_list = self.connection.system.listInactiveSystems(self.key)
            systemids = [info['id'] for info in inactive_system_list]
        return systemids

    def get_inactive_details(self, sid):
        """
         get's system details for an inactive system
        """
        details = {}
        details["id"] = sid
        details.update(self.connection.system.getCustomValues(self.key, sid))
        details["cpu_info"] = self.connection.system.getCpu(self.key, sid)
        details.update(self.connection.system.getMemory(self.key, sid))
        details.update(self.connection.system.getNetwork(self.key, sid))
        details["network_devices"] = self.connection.system.getNetworkDevices(self.key, sid)
        sys_details = self.connection.system.getDetails(self.key, sid)
        name_details = self.connection.system.getName(self.key, sid)

        details["inactive"] = {}
        details["inactive"]["last_boot"] = sys_details["last_boot"]
        details["inactive"]["last_checkin"] = name_details["last_checkin"]
        details["name"] = name_details["name"]
        details["last_checkin"] = datetime.now(tzutc()).strftime("%Y%m%dT%H:%M:%S")
        
        base_channel = self.connection.system.getSubscribedBaseChannel(self.key, sid)
        child_channels = self.connection.system.listSubscribedChildChannels(self.key, sid)
        #print "sub_base_channel = %s" % (base_channel)
        #print "sub_child_channels = %s" % (child_channels)
        channels = []
        channels.append({"channel_id":base_channel["id"], "channel_label":base_channel["label"]})
        for child in child_channels:
            channels.append({"channel_id":child["id"], "channel_label":child["label"]})
    
        details["subscribed_channels"] = channels
        
        return details

    def get_inactive_systems_details(self, system_ids):
        """
         get system details for all system ids
        """
        system_details = []
        for sid in system_ids:
            try:
                details = self.get_inactive_details(sid)
                if details:
                    system_details.append(details)
            except Exception, e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                print "Caught exception from system id '%s': %s" % (sid, e)
                print "\n".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        return system_details

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


def main():
    parser = OptionParser()
    parser.add_option("-s", "--server", dest="server",
        help="Name of the spacewalk server")
    parser.add_option("-u", "--username", dest="username",
        help="Login name to the spacewalk server")
    parser.add_option("-p", "--password", dest="password",
        help="Password to the spacewalk server")
    parser.add_option("-i", "--inactive", action="store_true", dest="inactive",
        help="Process Inactive Systems", default=False)

    (options, args) = parser.parse_args()

    client = SpacewalkClient(options.server, options.username, options.password)
    if options.inactive:
        inactive_systems = client.get_inactive_systems()
        system_details = client.get_inactive_systems_details(inactive_systems)
    else:
        active_systems = client.get_active_systems()
        system_details = client.get_active_systems_details(active_systems)

    system_facts_by_id= {}
    for system in system_details:
        system_facts_by_id[system['id']] = facts.translate_sw_facts_to_subsmgr(system)
    client.logout()
    pprint.pprint(system_facts_by_id)

if __name__ == "__main__":
    main()
