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
import time
import os
import sys
import logging
import logging.config

from spacewalk_splice_tool import facts, connect, utils, constants
from spacewalk_splice_tool.sw_client import SpacewalkClient
from spacewalk_splice_tool.cpin_connect import CandlepinConnection
from certutils import certutils
from datetime import datetime
from dateutil.tz import tzutc

_LIBPATH = "/usr/share/rhsm"
# add to the path if need be
if _LIBPATH not in sys.path:
    sys.path.append(_LIBPATH)

from subscription_manager.certdirectory import CertificateDirectory

from splice.common.connect import BaseConnection

CONFIG = utils.cfg_init(config_file=constants.SPLICE_CHECKIN_CONFIG)

def init_logging():
    log_config = CONFIG.get("logging", "config")
    if log_config:
        try:
            logging.config.fileConfig(log_config)
        except Exception, e:
            print e
            print "Unable to initialize logging config with: %s" % log_config

init_logging()
_LOG = logging.getLogger(__name__)

def get_product_ids(subscribedchannels, clone_map):
    """
    For the subscribed base and child channels look up product ids
    """
    _LOG.info("Translating subscribed channel data to product ids")
    channel_mappings = utils.read_mapping_file(constants.CHANNEL_PRODUCT_ID_MAPPING)
    product_ids = []
    for channel in subscribedchannels:
        # grab the origin
        origin_channel = clone_map[channel['channel_label']]
        if origin_channel in channel_mappings:
            cert = channel_mappings[origin_channel]
            product_ids.append(cert.split('-')[-1].split('.')[0])
    # reformat to how candlepin expects the product id list
    # TODO: extremely inefficient to load this per-call!
    cert_dir = CertificateDirectory("/usr/share/rhsm/product/RHEL-6/")
    installed_products = []
    for p in product_ids:
        product_cert = cert_dir.findByProduct(str(p))
        installed_products.append({"productId": product_cert.products[0].id, "productName": product_cert.products[0].name})
    return installed_products


def get_splice_serv_id():
    """
    return the splice server UUID to be used
    """
    cutils = certutils.CertUtils()
    return cutils.get_subject_pieces(open(CONFIG.get("splice", "splice_id_cert")).read(), ['CN'])['CN']

def transform_to_consumers(system_details):
    """
    Convert system details to candlepin consumers. Note that this is an ersatz
    consumer that gets processed again later, you cannot pass this directly
    into candlepin.
    """
    _LOG.info("Translating system details to candlepin consumers")
    _LOG.info("full detail list: %s" % system_details)
    consumer_list = []
    for details in system_details:
        _LOG.info("parsing detail: %s" % details)
        facts_data = facts.translate_sw_facts_to_subsmgr(details)
        consumer = dict()
        consumer['id'] = details['candlepin_uuid']
        consumer['facts'] = facts_data
        # TODO: don't hard code this!
        consumer['owner'] = 'admin'
        consumer['name'] = details['name']
        consumer['last_checkin'] = details['last_checkin']
        consumer['installed_products'] = details['installed_products']

        consumer_list.append(consumer)
    return consumer_list



def build_server_metadata(cfg):
    """
    Build splice server metadata obj
    """
    _LOG.info("building server metadata")
    server_metadata = {}
    cutils = certutils.CertUtils()
    server_metadata['description'] = cfg["splice_server_description"]
    server_metadata['environment'] = cfg["splice_server_environment"]
    server_metadata['hostname'] = cfg["splice_server_hostname"]
    server_metadata['uuid'] = cutils.get_subject_pieces(open(cfg["cert"]).read(), ['CN'])['CN']
    server_metadata['created'] = datetime.now(tzutc()).isoformat()
    server_metadata['modified'] = server_metadata['created']
    # wrap obj for consumption by upstream rcs
    _LOG.info("Built follow for server metadata '%s'" % (server_metadata))
    return {"objects": [server_metadata]}

def upload_to_candlepin(consumers, sw_client):
    """
    Uploads consumer data to candlepin
    """
    candlepin_conn = CandlepinConnection()

    for consumer in consumers:
        print "last checkin: %s" % consumer['last_checkin']
        if consumer.get('id', None):
            candlepin_conn.updateConsumer(uuid=consumer['id'],
                                          facts=consumer['facts'],
                                          installed_products=consumer['installed_products'],
                                          last_checkin=consumer['last_checkin'])
        else:
            # if we don't have a candlepin ID for this system, treat as a new system
            uuid = candlepin_conn.createConsumer(name=consumer['name'],
                                                facts=consumer['facts'],
                                                installed_products=consumer['installed_products'],
                                                last_checkin=consumer['last_checkin'])
            sw_client.set_candlepin_uuid(consumer['facts']['systemid'], uuid)
            

def get_checkin_config():
    return {
        "host" : CONFIG.get("splice", "hostname"),
        "port" : CONFIG.getint("splice", "port"),
        "handler" : CONFIG.get("splice", "handler"),
        "cert" : CONFIG.get("splice", "splice_id_cert"),
        "key" : CONFIG.get("splice", "splice_id_key"),
        "ca" : CONFIG.get("splice", "splice_ca_cert"),
        "splice_server_environment" : CONFIG.get("splice", "splice_server_environment"),
        "splice_server_hostname" : CONFIG.get("splice", "splice_server_hostname"),
        "splice_server_description" : CONFIG.get("splice", "splice_server_description"),
    }

def main():
    # performs the data capture, translation and checkin to candlepin
    parser = OptionParser()
    parser.add_option("-s", "--server", dest="server", default=None,
        help="Name of the spacewalk server")
    parser.add_option("-u", "--username", dest="username", default=None,
        help="Login name to the spacewalk server")
    parser.add_option("-p", "--password", dest="password", default=None,
        help="Password to the spacewalk server")

    (options, args) = parser.parse_args()
    hostname = options.server or CONFIG.get("satellite", "hostname")
    username = options.username or CONFIG.get("satellite", "username")
    password = options.password or CONFIG.get("satellite", "password")
    client = SpacewalkClient(hostname, username=username, password=password)
    _LOG.info("Established connection with server %s" % hostname)
    # get the system group to rhic mappings
    rhic_sg_map =  utils.read_mapping_file(CONFIG.get("splice", "rhic_mappings"))
    start_time = time.time()
    consumers = []
    # build the clone mapping
    clone_mapping = {}
    for label in client.get_channel_list():
        clone_mapping[label] = client.get_clone_origin_channel(label)
    _LOG.info("clone map: %s" % clone_mapping)
    _LOG.info("Started capturing system data from spacewalk server and transforming to candlepin model")
    for system_group, rhic_uuid in rhic_sg_map.items():
        # get list of active systems per system group
        active_systems = client.get_active_systems(system_group=system_group)
        system_details = client.get_active_systems_details(active_systems)
        inactive_systems = client.get_inactive_systems(system_group=system_group)
        inactive_system_details = client.get_inactive_systems_details(inactive_systems)
        system_details.extend(inactive_system_details)
        _LOG.info("full detail list (pre-transform): %s" % system_details)

        # enrich with candlepin uuid if available
        map(lambda details : details.update({'candlepin_uuid' : client.get_candlepin_uuid(details['id'])}), system_details)
        # enrich with engineering product IDs
        map(lambda details :
                details.update({'installed_products' : get_product_ids(details['subscribed_channels'],
                                clone_mapping)}), system_details)

        # convert the system details to candlepin consumers
        consumers.extend(transform_to_consumers(system_details))

    _LOG.info("consumers (post transform): %s" % consumers)
    upload_to_candlepin(consumers, client)
    finish_time = time.time() - start_time

if __name__ == "__main__":
    main()
