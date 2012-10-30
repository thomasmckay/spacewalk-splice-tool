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
from optparse import OptionParser
import pprint
import os

from spacewalk_splice_tool import facts, connect, utils, constants
from spacewalk_splice_tool.sw_client import SpacewalkClient
from certutils import certutils

config = utils.cfg_init(config_file=constants.SPLICE_CHECKIN_CONFIG)

def get_product_ids(subsribedchannels):
    """
    For the subscribed base and child channels look up product ids
    """
    channel_mappings = utils.read_mapping_file(constants.CHANNEL_PRODUCT_ID_MAPPING)
    product_ids = []
    for channel in subsribedchannels:
        if channel['channel_label'] in channel_mappings:
            cert = channel_mappings[channel['channel_label']]
            product_ids.append(cert.split('-')[-1].split('.')[0])
    return product_ids


def get_splice_serv_id():
    """
    Lookup the splice server id cert from /etc/pki/consumer/
    """
    cutils = certutils.CertUtils()
    cert_cn = cutils.get_subject_pieces(open(config.get("splice", "splice_id_cert")).read(), ['CN'])['CN']
    return cert_cn


def product_usage_model(system_details):
    """
    Convert system details to product usage model
    """
    product_usage_list = []
    for details in system_details:
        facts_data = facts.translate_sw_facts_to_subsmgr(details)
        product_usage = dict()
        # last_checkin time is UTC
        product_usage['date'] = details['last_checkin'].value
        product_usage['consumer'] = details['rhic_uuid']
        product_usage['instance_identifier'] = facts_data['net_dot_interface_dot_eth0_dot_mac_address']
        product_usage['allowed_product_info'] = get_product_ids(details['subscribed_channels'])
        product_usage['unallowed_product_info'] = []
        product_usage['facts'] = facts_data
        product_usage['splice_server'] = get_splice_serv_id()
        product_usage_list.append(product_usage)
    return product_usage_list


def upload(data):
    """
    Uploads the product usage model data to splice server
    """
    try:
        cfg = get_checkin_config()
        splice_conn = connect.BaseConnection(cfg["host"], cfg["port"], cfg["handler"],
            cert_file=cfg["cert"], key_file=cfg["key"], ca_cert=cfg["ca"])
        # upload the data to rcs
        splice_conn.POST("/v1/productusage/", data)
        utils.systemExit(os.EX_OK, "Successfully uploaded product usage data")
    except Exception, e:
        utils.systemExit(os.EX_DATAERR, "Error uploading ProductUsage Data; Error: %s" % e)

def get_checkin_config():
    return {
        "host" : config.get("splice", "hostname"),
        "port" : config.getint("splice", "port"),
        "handler" : config.get("splice", "handler"),
        "cert" : config.get("splice", "splice_id_cert"),
        "key" : config.get("splice", "splice_id_key"),
        "ca" : config.get("splice", "splice_ca_cert"),
    }

def main():
    # performs the data capture, translation and checkin to splice server
    parser = OptionParser()
    parser.add_option("-s", "--server", dest="server", default=None,
        help="Name of the spacewalk server")
    parser.add_option("-u", "--username", dest="username", default=None,
        help="Login name to the spacewalk server")
    parser.add_option("-p", "--password", dest="password", default=None,
        help="Password to the spacewalk server")

    (options, args) = parser.parse_args()
    hostname = options.server or config.get("satellite", "hostname")
    username = options.username or config.get("satellite", "username")
    password = options.password or config.get("satellite", "password")
    client = SpacewalkClient(hostname, username=username, password=password)
    # get the system group to rhic mappings
    rhic_sg_map =  utils.read_mapping_file(config.get("splice", "rhic_mappings"))
    product_usage_data = []
    for system_group, rhic_uuid in rhic_sg_map.items():
        # get list of active systems per system group
        active_systems = client.get_active_systems(system_group=system_group)
        # get system details for all active systems
        system_details = client.get_active_systems_details(active_systems)
        # include rhic_uuid in system details as if spacewalk is returning it
        map(lambda details : details.update({'rhic_uuid' : rhic_uuid}), system_details)
        # convert the system details to product usage model
        product_usage_data.extend(product_usage_model(system_details))
#    pprint.pprint(product_usage_data)
    upload(product_usage_data)

if __name__ == "__main__":
    main()