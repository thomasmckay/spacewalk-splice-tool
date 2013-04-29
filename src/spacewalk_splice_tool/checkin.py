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
import json
import pprint
import time
import os
import re
import sys
import logging

from spacewalk_splice_tool import facts, connect, utils, constants
from spacewalk_splice_tool.sw_client import SpacewalkClient
from spacewalk_splice_tool.cpin_connect import CandlepinConnection, NotFoundException
from certutils import certutils
from datetime import datetime
from dateutil.tz import tzutc

_LIBPATH = "/usr/share/rhsm"
# add to the path if need be
if _LIBPATH not in sys.path:
    sys.path.append(_LIBPATH)

from subscription_manager.certdirectory import CertificateDirectory
from splice.common.connect import BaseConnection
import splice.common.utils

_LOG = logging.getLogger(__name__)
CONFIG = utils.cfg_init(config_file=constants.SPLICE_CHECKIN_CONFIG)

SAT_OWNER_PREFIX = 'satellite-'

def get_product_ids(subscribedchannels, clone_map):
    """
    For the subscribed base and child channels look up product ids
    """
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
    retval['organization'] = consumer['owner']
    retval['name'] = consumer['name']
    retval['service_level'] = consumer['serviceLevel']
    # these two fields are populated by rcs
    retval['created'] = ""
    retval['updated'] = ""
    retval['instance_identifier'] = consumer['uuid']
    retval['entitlement_status'] = consumer['entitlementStatus']
    retval['organization_id'] = consumer['owner']['key']
    retval['organization_name'] = consumer['owner']['displayName']
    return retval


def transform_to_consumers(system_details):
    """
    Convert system details to candlepin consumers. Note that this is an ersatz
    consumer that gets processed again later, you cannot pass this directly
    into candlepin.
    """
    _LOG.info("Translating system details to candlepin consumers")
    consumer_list = []
    for details in system_details:
        facts_data = facts.translate_sw_facts_to_subsmgr(details)
        consumer = dict()
        consumer['id'] = details['server_id']
        consumer['facts'] = facts_data
        consumer['owner'] = details['org_id']
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
    return {"objects": [server_metadata]}

def get_candlepin_consumers():
    candlepin_conn = CandlepinConnection()
    return candlepin_conn.getConsumers()

def get_candlepin_entitlements(uuid):
    candlepin_conn = CandlepinConnection()
    return candlepin_conn.getEntitlements(uuid)

def get_candlepin_consumer_facts(uuid):
    candlepin_conn = CandlepinConnection()
    return candlepin_conn.getConsumer(uuid)['facts']

def write_sample_json(sample_json, rules_data, pool_data, product_data, mpu_data, splice_server_data):
    def write_file(file_name, data):
        if not data:
            return
        if not os.path.exists(sample_json):
            _LOG.info("Directory doesn't exist: %s" % (sample_json))
            return
        target_path = os.path.join(sample_json, file_name)
        try:
            _LOG.info("Will write json data to: %s" % (target_path))
            f = open(target_path, "w")
            try:
                f.write(splice.common.utils.obj_to_json(data, indent = 4))
            finally:
                f.close()
        except Exception, e:
            _LOG.exception("Unable to write sample json for: %s" % (target_path))
    write_file("sst_rules.json", rules_data)
    write_file("sst_pool.json", pool_data)
    write_file("sst_product.json", product_data)
    write_file("sst_mpu.json", mpu_data)
    write_file("sst_splice_server.json", splice_server_data)

def upload_to_rcs(rules_data, pool_data, product_data, mpu_data, sample_json=None):
    try:
        cfg = get_checkin_config()
        splice_conn = BaseConnection(cfg["host"], cfg["port"], cfg["handler"],
            cert_file=cfg["cert"], key_file=cfg["key"], ca_cert=cfg["ca"])

        splice_server_data = build_server_metadata(cfg)
        if sample_json:
            write_sample_json(sample_json=sample_json, rules_data=rules_data, 
                pool_data=pool_data, product_data=product_data,
                mpu_data=mpu_data, splice_server_data=splice_server_data)

        # upload the server metadata to rcs
        _LOG.info("sending metadata to server")
        url = "/v1/spliceserver/"
        status, body = splice_conn.POST(url, splice_server_data)
        _LOG.info("POST to %s: received %s %s" % (url, status, body))
        if status != 204:
            _LOG.error("Splice server metadata was not uploaded correctly")
            utils.systemExit(os.EX_DATAERR, "Error uploading splice server data")

        # upload the data to rcs
        url = "/v1/marketingproductusage/"
        status, body = splice_conn.POST(url, mpu_data)
        _LOG.info("POST to %s: received %s %s" % (url, status, body))
        if status != 202 and status != 204:
            _LOG.error("MarketingProductUsage data was not uploaded correctly")
            utils.systemExit(os.EX_DATAERR, "Error uploading marketing product usage data")

        # Upload Rules
        #url = "/v1/rules/"
        #status, body = splice_conn.POST(url, rules_data)
        #_LOG.info("POST to %s: received %s %s" % (url, status, body))
        #if status != 202 and status != 204:
        #    _LOG.error("Rules data was not uploaded correctly")
        #    utils.systemExit(os.EX_DATAERR, "Error uploading rules data")
        #
        ## Upload Pools
        #url = "/v1/pool/"
        #status, body = splice_conn.POST(url, pool_data)
        #_LOG.info("POST to %s: received %s %s" % (url, status, body))
        #if status != 202 and status != 204:
        #    _LOG.error("Pool data was not uploaded correctly")
        #    utils.systemExit(os.EX_DATAERR, "Error uploading pool data")
        #
        ## Upload Products
        #url = "/v1/product/"
        #status, body = splice_conn.POST(url, product_data)
        #_LOG.info("POST to %s: received %s %s" % (url, status, body))
        #if status != 202 and status != 204:
        #    _LOG.error("Products data was not uploaded correctly")
        #    utils.systemExit(os.EX_DATAERR, "Error uploading products data")

        utils.systemExit(os.EX_OK, "Upload was successful")
    except Exception, e:
        _LOG.error("Error uploading MarketingProductUsage Data; Error: %s" % e)
        utils.systemExit(os.EX_DATAERR, "Error uploading; Error: %s" % e)

def update_owners(cpin_client, orgs):
    """
    ensure that the candlepin owner set matches what's in spacewalk
    """

    owners = cpin_client.getOwners()
    org_ids = orgs.keys()
    owner_labels = map(lambda x: x['label'], owners)

    for org_id in org_ids:
        katello_label = SAT_OWNER_PREFIX + org_id
        if katello_label not in owner_labels:
            _LOG.info("creating owner %s (%s), owner is in spacewalk but not katello" % (katello_label, orgs[org_id]))
            cpin_client.createOwner(label=katello_label, name=orgs[org_id])
            cpin_client.createOrgAdminRolePermission(kt_org_label=katello_label)

    # get the owner list again
    owners = cpin_client.getOwners()
    # build up a label->name mapping this time
    owner_labels_names = {}
    for owner in owners:
        owner_labels_names[owner['label']] = owner['name']

    # perform deletions
    for owner_label in owner_labels_names.keys():
        # bail out if this isn't an owner we are managing
        if not owner_label.startswith(SAT_OWNER_PREFIX):
            continue
        
        # get the org ID from the katello name
        kt_org_id = owner_label[len(SAT_OWNER_PREFIX):]
        if kt_org_id not in org_ids:
            _LOG.info("removing owner %s (name: %s), owner is no longer in spacewalk" % (owner_label, owner_labels_names[owner_label]))
            cpin_client.deleteOwner(name=owner_labels_names[owner_label])
            

def update_users(cpin_client, sw_userlist):
    """
    ensure that the katello user set matches what's in spacewalk
    """

    sw_users = {}
    for sw_user in sw_userlist:
        sw_users[sw_user['username']] = sw_user
    kt_users = {}
    for kt_user in cpin_client.getUsers():
        kt_users[kt_user['username']] = kt_user

    for sw_username in sw_users.keys():
        if sw_username not in kt_users.keys():
            _LOG.info("adding new user %s to katello" % sw_username)
            created_kt_user = cpin_client.createUser(username=sw_username, email=sw_users[sw_username]['email']) 

def update_roles(cpin_client, sw_userlist):
    sw_users = {}
    for sw_user in sw_userlist:
        sw_users[sw_user['username']] = sw_user
    kt_users = {}
    for kt_user in cpin_client.getUsers():
        kt_users[kt_user['username']] = kt_user

    for kt_username in kt_users.keys():
        # if the user isn't also in SW, bail out
        # NB: we assume kt_users is always be a superset of sw_users
        if kt_username not in sw_users.keys():
            _LOG.info("skipping role sync for %s, user is not in spacewalk" % kt_username)
            continue

        # get a flat list of role names, for comparison with sw
        kt_roles = map(lambda x: x['name'], cpin_client.getRoles(user_id = kt_users[kt_username]['id']))
        sw_roles = sw_users[kt_username]['role'].split(';')
        sw_user_org = sw_users[kt_username]['organization_id']


        # add any new roles
        for sw_role in sw_roles:
            _LOG.debug("examining sw role %s for org %s against kt role set %s" % (sw_role, sw_user_org,  kt_roles))
            if sw_role == 'Organization Administrator' and \
                "Org Admin Role for satellite-%s" % sw_user_org not in kt_roles:
                    _LOG.info("adding %s to %s org admin role in katello" % (kt_username, "satellite-%s" % sw_user_org))
                    cpin_client.grantOrgAdmin(
                        kt_user=kt_users[kt_username], kt_org_label = "satellite-%s" % sw_user_org)
            elif sw_role == 'Satellite Administrator' and 'Administrator' not in kt_roles:
                    _LOG.info("adding %s to full admin role in katello" % kt_username)
                    cpin_client.grantFullAdmin(kt_user=kt_users[kt_username])

        # delete any roles in kt but not sw
        for kt_role in kt_roles:
            # TODO: handle sat admin
            _LOG.debug("examining kt role %s against sw role set %s for org %s" % (kt_role, sw_roles, sw_user_org))
            if kt_role == "Org Admin Role for satellite-%s" % sw_users[kt_username]['organization_id'] and \
                "Organization Administrator" not in sw_roles:
                _LOG.info("removing %s from %s org admin role in katello" % (kt_username, "satellite-%s" % sw_user_org))
                cpin_client.ungrantOrgAdmin(kt_user=kt_users[kt_username],
                                kt_org_label = "satellite-%s" % sw_user_org)
            elif kt_role == 'Administrator' and sw_role != 'Satellite Administrator':
                    _LOG.info("removing %s from full admin role in katello" % kt_username)
                    cpin_client.ungrantFullAdmin(kt_user=kt_users[kt_username])
                

def delete_stale_consumers(cpin_client, consumer_list, system_list):
    """
    removes consumers that are in candlepin and not spacewalk. This is to clean
    up any systems that were deleted in spacewalk.
    """

    system_id_list = map(lambda x: x['server_id'], system_list)

    owner_labels = {}
    owner_list = cpin_client.getOwners()
    for owner in owner_list:
        owner_labels[owner['id']] = owner['label']
    
  
    consumers_to_delete = [] 
    for consumer in consumer_list:
        # don't delete consumers that are not in orgs we manage!
        if not owner_labels[consumer['environment']['organization_id']].startswith(SAT_OWNER_PREFIX):
            continue
        if consumer['name'] not in system_id_list:
            consumers_to_delete.append(consumer)

    
    _LOG.info("removing %s consumers that are no longer in spacewalk" % len(consumers_to_delete))
    for consumer in consumers_to_delete:
        cpin_client.deleteConsumer(consumer['uuid'])

def upload_to_candlepin(consumers, sw_client, cpin_client):
    """
    Uploads consumer data to candlepin
    """

    # XXX: confusing
    consumers_from_kt = cpin_client.getConsumers()
    sysids_to_uuids = {}
    for consumer in consumers_from_kt:
        sysids_to_uuids[consumer['name']] = consumer['uuid']
    sw_sysids_from_kt = map(lambda x: x['name'], consumers_from_kt)

    for consumer in consumers:
        if consumer['id'] in sw_sysids_from_kt:
            # TODO: fix confusing first arg
            cpin_client.updateConsumer(cp_uuid=sysids_to_uuids[consumer['id']],
                                          sw_id = consumer['id'],
                                          facts=consumer['facts'],
                                          installed_products=consumer['installed_products'],
                                          owner=consumer['owner'],
                                          last_checkin=consumer['last_checkin'])
        else:

            # TODO: FIX UUID TO NAME SHENANIGANS IN CPIN_CONNECT
            uuid = cpin_client.createConsumer(name='unused-field',
                                                uuid=consumer['id'],
                                                facts=consumer['facts'],
                                                installed_products=consumer['installed_products'],
                                                last_checkin=consumer['last_checkin'],
                                                owner=consumer['owner'])

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

def build_rcs_data(data):
    """
    wraps the data in the right format for uploading
    """
    return {"objects": data}


def get_parent_channel(channel, channels):
    for c in channels:
        if c['new_channel_label'] == channel['original_channel_label']:
            return get_parent_channel(c, channels)
    return channel
    

def channel_mapping(channels):
    channel_map = {}

    for channel in channels:
        parent_channel = get_parent_channel(channel, channels)
        channel_map[channel['new_channel_label']] = \
            parent_channel['original_channel_label']

    return channel_map


def update_system_channel(systems, channels):

    channel_map = channel_mapping(channels)
    for system in systems:
        system['software_channel'] = channel_map.get(
                                        system['software_channel'],
                                        system['software_channel'])


def spacewalk_sync(options):
    """
    Performs the data capture, translation and checkin to candlepin
    """
    client = SpacewalkClient()
    cpin_client = CandlepinConnection()
    consumers = []

    _LOG.info("Started capturing system data from spacewalk database and transforming to candlepin model")
    _LOG.info("retrieving data from spacewalk")
    sw_user_list = client.get_user_list()
    system_details = client.get_system_list()
    channel_details = client.get_channel_list()
    update_system_channel(system_details, channel_details)
    org_list = client.get_org_list()

    update_owners(cpin_client, org_list)
    update_users(cpin_client, sw_user_list)
    update_roles(cpin_client, sw_user_list)

    cpin_consumer_list = cpin_client.getConsumers()


    delete_stale_consumers(cpin_client, cpin_consumer_list, system_details)


    # build the clone mapping
    _LOG.info("enriching %s spacewalk records" % len(system_details))
    # enrich with engineering product IDs
    clone_mapping = []
    map(lambda details :
            details.update({'installed_products' : get_product_ids(details['software_channel'],
                            clone_mapping)}), system_details)

    # convert the system details to candlepin consumers
    consumers.extend(transform_to_consumers(system_details))
    _LOG.info("found %s systems to upload into candlepin" % len(consumers))
    _LOG.info("uploading to candlepin...")
    upload_to_candlepin(consumers, client, cpin_client)
    _LOG.info("upload completed")


def splice_sync(options):
    """
    Syncs data from candlepin to splice
    """
    _LOG.info("downloading consumers from candlepin")
    # now pull put out of candlepin, and into rcs!
    cpin_consumers = get_candlepin_consumers()
    cpin_client = CandlepinConnection()
    _LOG.info("creating marketingproductusage objects")

    # create the base marketing usage list
    rcs_mkt_usage = map(transform_to_rcs, cpin_consumers)
    # enrich with facts
    map(lambda rmu : 
            rmu.update(
                {'facts': transform_facts_to_rcs(
                            get_candlepin_consumer_facts(
                                rmu['instance_identifier']))}), rcs_mkt_usage)
    # enrich with product usage info
    map(lambda rmu : 
            rmu.update(
                {'product_info': transform_entitlements_to_rcs(
                                    get_candlepin_entitlements(
                                        rmu['instance_identifier']))}), 
                                        rcs_mkt_usage)
    
    #rules_data = cpin_client.getRules()
    #pool_data = cpin_client.getPools()
    #product_data = cpin_client.getProducts()

    _LOG.info("uploading to RCS")
    upload_to_rcs(rules_data=build_rcs_data([rules_data]), 
        pool_data=build_rcs_data(pool_data), 
        product_data=build_rcs_data(product_data), 
        mpu_data=build_rcs_data(rcs_mkt_usage), 
                                sample_json=options.sample_json)
    _LOG.info("upload completed")


def main(options):

    start_time = time.time()
    _LOG.info("run starting")

    if options.spacewalk_sync:
        spacewalk_sync(options)
    elif options.splice_sync:
        splice_sync(options)
    else:
        spacewalk_sync(options)
        splice_sync(options)

    finish_time = time.time() - start_time
    _LOG.info("run complete") 


if __name__ == "__main__":
    parser = OptionParser(description="Spacewalk Splice Tool")
    parser.add_option('--sample_json', action="store", default=None,
        help="Specify a directory to write the json data sent to Splice, if not specified no data is written to file.")
    (opts, args) = parser.parse_args()
    main(sample_json=opts.sample_json)
