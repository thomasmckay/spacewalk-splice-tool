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

import pprint
import xmlrpclib
from optparse import OptionParser

import facts

class SpacewalkClient(object):
    
    def __init__(self, serverurl, username, password):
        self.server = serverurl
        self.username = username
        self.password = password
        self.connection = xmlrpclib.Server(serverurl, verbose=0)
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
        system_details = self.connection.system.listActiveSystemDetails(self.key, active_system_ids)
        return system_details

def main():
    parser = OptionParser()
    parser.add_option("-s", "--server", dest="server",
        help="Name of the spacewalk server")
    parser.add_option("-u", "--username", dest="username",
        help="Login name to the spacewalk server")
    parser.add_option("-p", "--password", dest="password",
        help="Password to the spacewalk server")

    (options, args) = parser.parse_args()

    SERVER_URL = "https://" + options.server + "/rpc/api"
    client = SpacewalkClient(SERVER_URL, username=options.username, password=options.password)
    active_systems = client.get_active_systems()
    system_details = client.get_active_systems_details(active_systems)
    system_facts_by_id= {}
    for system in system_details:
        system_facts_by_id[system['id']] = facts.translate_sw_facts_to_subsmgr(system)
    client.logout()
    pprint.pprint(system_details)
    

if __name__ == "__main__":
    main()