#!/usr/bin/python

import xmlrpclib
import pprint
from optparse import OptionParser

def get_origin(conn, key, label):
    # walk up the channel->origin tree until we get to the root
    original_channel = conn.channel.software.getDetails(key, label)['clone_original']
    if original_channel:
        return get_origin(conn, key, original_channel)
    return label
        

def get_clone_mapping(conn, key):
    channel_list = conn.channel.listSoftwareChannels(key)
    # strip the full channel list to just the labels
    labels = map(lambda x : x['label'], channel_list)
    return map(lambda x: {x: get_origin(conn, key, x)}, labels)


def get_active_systems(conn, key):
    # get list of all active systems
    active_system_list = conn.system.listActiveSystems(key)
    systemids = []
    for info in active_system_list:
	systemid = {}
	systemid['id'] = info['id']
	systemid['last_checkin'] = info['last_checkin']
	systemids.append(systemid)
    return systemids

def get_active_systems_details(conn, key, active_systems):
    # get system details
    system_details = {}
    for system in active_systems:
        sysid = system['id']
        system_details[sysid] = {}
        system_details[sysid]["details"] =  conn.system.getDetails(key, sysid)
        # get entitlement details ( currently this only returns system entitlements )
        system_details[sysid]["entitlements"] = conn.system.getEntitlements(key, sysid)
        # subscribed base channel
        system_details[sysid]["subscribed_base_channel"] = conn.system.getSubscribedBaseChannel(key, sysid)
        # subscribed child channels
        system_details[sysid]["subscribed_child_channel"] = conn.system.listSubscribedChildChannels(key,sysid)
        # get memory
        system_details[sysid]["memory"] = conn.system.getMemory(key, sysid)
        # get CPU info
        system_details[sysid]["cpu"] = conn.system.getCpu(key, sysid)
        # get Dmi info
        system_details[sysid]["dmi"] = conn.system.getDmi(key, sysid)
        # get Network Devices
        system_details[sysid]["net_devices"] = conn.system.getNetworkDevices(key, sysid)
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
    # set up the server connection
    conn = xmlrpclib.Server(SERVER_URL, verbose=0)
    # login to server and grab authentication credentials
    key = conn.auth.login(options.username, options.password)

    active_systems = get_active_systems(conn, key)
    print active_systems
    clone_mapping = get_clone_mapping(conn, key)
    print clone_mapping
    system_details = get_active_systems_details(conn, key, active_systems)
    pprint.pprint(system_details)
    conn.auth.logout(key)

if __name__ == "__main__":
    main()
