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
import re
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
    for channel in subscribedchannels.split(';'):
        # grab the origin
        #origin_channel = clone_map[channel['channel_label']]
        origin_channel = channel
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

def transform_facts_to_rcs(facts):
    # rcs doesn't like the "." in fact names
    rcs_facts = {}
    
    for f in facts.keys():
        rcs_facts[f.replace('.', '_dot_')] = facts[f]

    return rcs_facts

def transform_entitlements_to_rcs(entitlements):
    rcs_ents = []
    for e in entitlements:
        rcs_ent = {}
        rcs_ent['account'] = e['accountNumber']
        rcs_ent['contract'] = e['contractNumber']
        rcs_ent['product'] = e['pool']['productId']
        rcs_ent['quantity'] = e['quantity']
        rcs_ents.append(rcs_ent)

    return rcs_ents
        
def _get_splice_server_uuid():
    """
    obtains the UUID that sst is emulating
    """
    cfg = get_checkin_config()
    cutils = certutils.CertUtils()
    return cutils.get_subject_pieces(open(cfg["cert"]).read(), ['CN'])['CN']

def transform_to_rcs(consumer):
    """
    convert a candlepin consumer into something parsable by RCS
    as a MarketingProductUsage obj
    """
    retval = {}
    retval['splice_server'] = _get_splice_server_uuid()
    retval['date'] = consumer['lastCheckin']
    # these two fields are populated by rcs
    retval['created'] = ""
    retval['updated'] = ""
    retval['instance_identifier'] = consumer['uuid']
    retval['entitlement_status'] = consumer['entitlementStatus']
    return retval


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
        consumer['id'] = details['server_id']
        consumer['facts'] = facts_data
        # TODO: don't hard code this!
        consumer['owner'] = 'admin'
        consumer['name'] = details['name']
        consumer['last_checkin'] = details['last_checkin_time']
        consumer['installed_products'] = details['installed_products']

        consumer_list.append(consumer)
    return consumer_list


def build_server_metadata(cfg):
    """
    Build splice server metadata obj
    """
    _LOG.info("building server metadata")
    server_metadata = {}
    server_metadata['description'] = cfg["splice_server_description"]
    server_metadata['environment'] = cfg["splice_server_environment"]
    server_metadata['hostname'] = cfg["splice_server_hostname"]
    server_metadata['uuid'] = _get_splice_server_uuid()
    server_metadata['created'] = datetime.now(tzutc()).isoformat()
    server_metadata['updated'] = server_metadata['created']
    # wrap obj for consumption by upstream rcs
    _LOG.info("Built follow for server metadata '%s'" % (server_metadata))
    return {"objects": [server_metadata]}

def get_candlepin_consumers():
    candlepin_conn = CandlepinConnection()
    return candlepin_conn.getConsumers()

def get_candlepin_entitlements(uuid):
    candlepin_conn = CandlepinConnection()
    return candlepin_conn.getEntitlements(uuid)

def get_candlepin_consumer_facts(uuid):
    candlepin_conn = CandlepinConnection()
    return candlepin_conn.getConsumerFacts(uuid)

def upload_to_rcs(data):
    try:
        cfg = get_checkin_config()
        splice_conn = BaseConnection(cfg["host"], cfg["port"], cfg["handler"],
            cert_file=cfg["cert"], key_file=cfg["key"], ca_cert=cfg["ca"])

        # upload the server metadata to rcs
        _LOG.info("sending metadata to server")
        url = "/v1/spliceserver/"
        status, body = splice_conn.POST(url, build_server_metadata(cfg))
        _LOG.info("POST to %s: received %s %s" % (url, status, body))
        if status != 204:
            _LOG.error("Splice server metadata was not uploaded correctly")
            utils.systemExit(os.EX_DATAERR, "Error uploading splice server data")
        # upload the data to rcs
        url = "/v1/marketingproductusage/"
        status, body = splice_conn.POST(url, data)
        _LOG.info("POST to %s: received %s %s" % (url, status, body))
        if status != 202 and status != 204:
            _LOG.error("ProductUsage data was not uploaded correctly")
            utils.systemExit(os.EX_DATAERR, "Error uploading product usage data")
        utils.systemExit(os.EX_OK, "Upload was successful")
    except Exception, e:
        _LOG.error("Error uploading MarketingProductUsage Data; Error: %s" % e)
        utils.systemExit(os.EX_DATAERR, "Error uploading; Error: %s" % e)

def delete_candlepin_consumsers(sw_client):
    """
    Finds all consumer UUIDs in candlepin that do not exist in spacewalk, and
    deletes from candlepin. This is to clean up any systems that were deleted in
    spacewalk.
    """
    candlepin_conn = CandlepinConnection()

    active_systems = get_active_systems(sw_client, key)
    system_uuids = set()
    for s in active_systems:
        system_uuids.add(sw_client.getNoteUuid(sw_client, key, s['id']))

    cc = CandlepinConnection()
    consumer_uuids = set()
    for consumer in cc.cp.getConsumers():
        consumer_uuids.add(consumer['uuid'])

    print "records in candlepin but not spacewalk: %s" % (consumer_uuids - system_uuids)

    for c in (consumer_uuids - system_uuids):
        print "removing %s" % c
        cc.cp.unregisterConsumer(c)

def upload_to_candlepin(consumers, sw_client):
    """
    Uploads consumer data to candlepin
    """
    candlepin_conn = CandlepinConnection()

    for consumer in consumers:
        if candlepin_conn.getConsumer(consumer['id']):
            candlepin_conn.updateConsumer(uuid=consumer['id'],
                                          facts=consumer['facts'],
                                          installed_products=consumer['installed_products'],
                                          last_checkin=consumer['last_checkin'])
        else:
            # if we don't have a candlepin ID for this system, treat as a new system
            uuid = candlepin_conn.createConsumer(name=consumer['name'],
                                                facts=consumer['facts'],
                                                installed_products=consumer['installed_products'],
                                                last_checkin=consumer['last_checkin'],
                                                uuid=consumer['id'])

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

def build_rcs_data(mkt_usage):
    """
    wraps the marketing usage data in the right format for uploading
    """
    return {"objects": mkt_usage}

def main():
    # performs the data capture, translation and checkin to candlepin
    client = SpacewalkClient()
    start_time = time.time()
    consumers = []
    # build the clone mapping
    _LOG.info("Started capturing system data from spacewalk database and transforming to candlepin model")
    print "retrieving data from spacewalk..."
    system_details = client.get_db_output()
    _LOG.info("full detail list (pre-transform): %s" % system_details)

    # enrich with engineering product IDs
    clone_mapping = []
    map(lambda details :
            details.update({'installed_products' : get_product_ids(details['software_channel'],
                            clone_mapping)}), system_details)

    # convert the system details to candlepin consumers
    consumers.extend(transform_to_consumers(system_details))
    _LOG.info("consumers (post transform): %s" % consumers)
    print "found %s systems to upload into candlepin" % len(consumers)
    print "uploading to candlepin..."
    upload_to_candlepin(consumers, client)
    print "done"
    # now pull put out of candlepin, and into rcs!
    cpin_consumers = get_candlepin_consumers()

    # create the base marketing usage list
    rcs_mkt_usage = map(transform_to_rcs, cpin_consumers)
    # enrich with facts
    map(lambda rmu : rmu.update({'facts' : transform_facts_to_rcs(get_candlepin_consumer_facts(rmu['instance_identifier']))}), rcs_mkt_usage)
    # enrich with product usage info
    map(lambda rmu : rmu.update({'product_info' : transform_entitlements_to_rcs(get_candlepin_entitlements(rmu['instance_identifier']))}), rcs_mkt_usage)
    
    upload_to_rcs(build_rcs_data(rcs_mkt_usage))


    # find any systems in candlepin that need to be deleted


    finish_time = time.time() - start_time

if __name__ == "__main__":
    main()
