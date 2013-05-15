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
import io
import json
import logging
from optparse import OptionParser
import os
import re
import socket
import sys
import tempfile
import time

from certutils import certutils
from dateutil.tz import tzutc
from splice.common.connect import BaseConnection
import splice.common.utils

from spacewalk_splice_tool import facts, connect, utils, constants
from spacewalk_splice_tool.sw_client import SpacewalkClient
from spacewalk_splice_tool.katello_connect import KatelloConnection, NotFoundException

_LIBPATH = "/usr/share/rhsm"
# add to the path if need be
if _LIBPATH not in sys.path:
    sys.path.append(_LIBPATH)

from subscription_manager.certdirectory import CertificateDirectory

_LOG = logging.getLogger(__name__)
CONFIG = None

SAT_OWNER_PREFIX = 'satellite-'

CERT_DIR_PATH = "/usr/share/rhsm/product/RHEL-6/"
CERT_DIR = None

def get_product_ids(subscribedchannels):
    """
    For the subscribed base and child channels look up product ids
    """
    if CERT_DIR is None:
        global CERT_DIR
        CERT_DIR = CertificateDirectory(CERT_DIR_PATH)

    mapping_file = os.path.join(
        os.path.join(constants.CHANNEL_PRODUCT_ID_MAPPING_DIR,
                     utils.get_release()),
        constants.CHANNEL_PRODUCT_ID_MAPPING_FILE)
    channel_mappings = utils.read_mapping_file(mapping_file)

    product_ids = []
    for channel in subscribedchannels.split(';'):
        origin_channel = channel
        if origin_channel in channel_mappings:
            cert = channel_mappings[origin_channel]
            product_ids.append(cert.split('-')[-1].split('.')[0])
    # reformat to how candlepin expects the product id list
    installed_products = []
    for p in product_ids:
        product_cert = CERT_DIR.findByProduct(str(p))
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
        rcs_ent['product'] = e['productId']
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
    convert a katello consumer into something parsable by RCS
    as a MarketingProductUsage obj
    """

    retval = {}

    retval['splice_server'] = _get_splice_server_uuid()
    retval['date'] = consumer['checkin_time']
    retval['name'] = consumer['name']
    retval['service_level'] = consumer['serviceLevel']
    # these two fields are populated by rcs
    retval['created'] = ""
    retval['updated'] = ""
    retval['hostname'] = consumer['facts']['network.hostname']
    retval['instance_identifier'] = consumer['uuid']
    retval['entitlement_status'] = consumer['entitlement_status']
    retval['organization_id'] = str(consumer['owner']['key'])
    retval['organization_name'] = consumer['owner']['displayName']
    retval['facts'] = transform_facts_to_rcs(consumer['facts'])
    return retval


def transform_to_consumers(system_details):
    """
    Convert system details to katello consumers. Note that this is an ersatz
    consumer that gets processed again later, you cannot pass this directly
    into katello.
    """
    _LOG.info("Translating system details to katello consumers")
    consumer_list = []
    for details in system_details:
        facts_data = facts.translate_sw_facts_to_subsmgr(details)
        # assume 3.1, so large certs can bind to this consumer
        facts_data['system.certificate_version'] = '3.1'
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

def get_katello_consumers():
    katello_conn = KatelloConnection()
    return katello_conn.getConsumers()

def get_katello_entitlements(uuid):
    katello_conn = KatelloConnection()
    return katello_conn.getEntitlements(uuid)

def write_sample_json(sample_json, mpu_data, splice_server_data):
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
    write_file("sst_mpu.json", mpu_data)
    write_file("sst_splice_server.json", splice_server_data)

def upload_to_rcs(mpu_data, sample_json=None):
    cfg = get_checkin_config()
    try:
        splice_conn = BaseConnection(cfg["host"], cfg["port"], cfg["handler"],
            cert_file=cfg["cert"], key_file=cfg["key"], ca_cert=cfg["ca"])

        splice_server_data = build_server_metadata(cfg)
        if sample_json:
            write_sample_json(sample_json=sample_json, mpu_data=mpu_data,
                            splice_server_data=splice_server_data)
        # upload the server metadata to rcs
        _LOG.info("sending metadata to server")
        url = "/v1/spliceserver/"
        status, body = splice_conn.POST(url, splice_server_data)
        _LOG.debug("POST to %s: received %s %s" % (url, status, body))
        if status != 204:
            _LOG.error("Splice server metadata was not uploaded correctly")
            utils.system_exit(os.EX_DATAERR, "Error uploading splice server data")

        # upload the data to rcs
        url = "/v1/marketingproductusage/"
        status, body = splice_conn.POST(url, mpu_data)
        _LOG.debug("POST to %s: received %s %s" % (url, status, body))
        if status != 202 and status != 204:
            _LOG.error("MarketingProductUsage data was not uploaded correctly")
            utils.system_exit(os.EX_DATAERR, "Error uploading marketing product usage data")

        utils.system_exit(os.EX_OK, "Upload was successful")
    except Exception, e:
        _LOG.error("Error uploading MarketingProductUsage Data; Error: %s" % e)
        utils.system_exit(os.EX_DATAERR, "Error uploading; Error: %s" % e)

def update_owners(katello_client, orgs):
    """
    ensure that the katello owner set matches what's in spacewalk
    """

    owners = katello_client.getOwners()
    org_ids = orgs.keys()
    owner_labels = map(lambda x: x['label'], owners)

    for org_id in org_ids:
        katello_label = SAT_OWNER_PREFIX + org_id
        if katello_label not in owner_labels:
            _LOG.info("creating owner %s (%s), owner is in spacewalk but not katello" % (katello_label, orgs[org_id]))
            katello_client.createOwner(label=katello_label, name=orgs[org_id])
            katello_client.createOrgAdminRolePermission(kt_org_label=katello_label)
            # if we are not the first org, create a distributor for us in the first org
            if org_id is not "1":
                _LOG.info("creating distributor for %s (org id: %s)" % (orgs[org_id], org_id)) 
                distributor = katello_client.createDistributor(name="Distributor for %s" % orgs[org_id], root_org='satellite-1')
                manifest_data = katello_client.exportManifest(dist_uuid = distributor['uuid'])
                # katello-cli does some magic that requires an actual file here
                manifest_file = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
                manifest_filename = manifest_file.name
                _LOG.info("manifest temp file is %s" % manifest_filename)
                manifest_file.write(manifest_data)
                manifest_file.close()
                manifest_file = open(manifest_filename, 'r')
        
                # this uses the org name, not label
                provider = katello_client.getRedhatProvider(org=orgs[org_id])
                katello_client.importManifest(prov_id=provider['id'], file = manifest_file)
                # explicit close to make sure the temp file gets deleted
                manifest_file.close()

    # get the owner list again
    owners = katello_client.getOwners()
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
            katello_client.deleteOwner(name=owner_labels_names[owner_label])
            

def update_users(katello_client, sw_userlist):
    """
    ensure that the katello user set matches what's in spacewalk
    """

    sw_users = {}
    for sw_user in sw_userlist:
        sw_users[sw_user['username']] = sw_user
    kt_users = {}
    for kt_user in katello_client.getUsers():
        kt_users[kt_user['username']] = kt_user

    for sw_username in sw_users.keys():
        if sw_username not in kt_users.keys():
            _LOG.info("adding new user %s to katello" % sw_username)
            created_kt_user = katello_client.createUser(username=sw_username, email=sw_users[sw_username]['email']) 

def update_roles(katello_client, sw_userlist):
    sw_users = {}
    for sw_user in sw_userlist:
        sw_users[sw_user['username']] = sw_user
    kt_users = {}
    for kt_user in katello_client.getUsers():
        kt_users[kt_user['username']] = kt_user

    for kt_username in kt_users.keys():
        # if the user isn't also in SW, bail out
        # NB: we assume kt_users is always be a superset of sw_users
        if kt_username not in sw_users.keys():
            _LOG.info("skipping role sync for %s, user is not in spacewalk" % kt_username)
            continue

        # get a flat list of role names, for comparison with sw
        kt_roles = map(lambda x: x['name'], katello_client.getRoles(user_id = kt_users[kt_username]['id']))
        sw_roles = sw_users[kt_username]['role'].split(';')
        sw_user_org = sw_users[kt_username]['organization_id']


        # add any new roles
        for sw_role in sw_roles:
            _LOG.debug("examining sw role %s for org %s against kt role set %s" % (sw_role, sw_user_org,  kt_roles))
            if sw_role == 'Organization Administrator' and \
                "Org Admin Role for satellite-%s" % sw_user_org not in kt_roles:
                    _LOG.info("adding %s to %s org admin role in katello" % (kt_username, "satellite-%s" % sw_user_org))
                    katello_client.grantOrgAdmin(
                        kt_user=kt_users[kt_username], kt_org_label = "satellite-%s" % sw_user_org)
            elif sw_role == 'Satellite Administrator' and 'Administrator' not in kt_roles:
                    _LOG.info("adding %s to full admin role in katello" % kt_username)
                    katello_client.grantFullAdmin(kt_user=kt_users[kt_username])

        # delete any roles in kt but not sw
        for kt_role in kt_roles:
            # TODO: handle sat admin
            _LOG.debug("examining kt role %s against sw role set %s for org %s" % (kt_role, sw_roles, sw_user_org))
            if kt_role == "Org Admin Role for satellite-%s" % sw_users[kt_username]['organization_id'] and \
                "Organization Administrator" not in sw_roles:
                _LOG.info("removing %s from %s org admin role in katello" % (kt_username, "satellite-%s" % sw_user_org))
                katello_client.ungrantOrgAdmin(kt_user=kt_users[kt_username],
                                kt_org_label = "satellite-%s" % sw_user_org)
            elif kt_role == 'Administrator' and sw_role != 'Satellite Administrator':
                    _LOG.info("removing %s from full admin role in katello" % kt_username)
                    katello_client.ungrantFullAdmin(kt_user=kt_users[kt_username])
                

def delete_stale_consumers(katello_client, consumer_list, system_list):
    """
    removes consumers that are in katello and not spacewalk. This is to clean
    up any systems that were deleted in spacewalk.
    """

    system_id_list = map(lambda x: x['server_id'], system_list)

    _LOG.debug("system id list from sw: %s" % system_id_list)
    consumers_to_delete = []
    for consumer in consumer_list:
        _LOG.debug("checking %s for deletion" % consumer['facts']['systemid'])
        # don't delete consumers that are not in orgs we manage!
        if not consumer['owner']['key'].startswith(SAT_OWNER_PREFIX):
            continue
        if consumer['facts']['systemid'] not in system_id_list:
            consumers_to_delete.append(consumer)
    
    _LOG.info("removing %s consumers that are no longer in spacewalk" % len(consumers_to_delete))
    for consumer in consumers_to_delete:
        _LOG.info("removed consumer %s" % consumer['name'])
        katello_client.deleteConsumer(consumer['uuid'])

def upload_host_guest_mapping(host_guests, katello_client):
    """
    updates katello consumers that have guests. This has to happen after an
    initial update, so we have UUIDs for all systems
    """
    pass

def upload_to_katello(consumers, katello_client):
    """
    Uploads consumer data to katello
    """

    # TODO: this can go away and be refactored to use findBySpacewalkID within
    # the loop
    consumers_from_kt = katello_client.getConsumers(with_details=False)
    names_to_uuids = {}
    for consumer in consumers_from_kt:
        names_to_uuids[consumer['name']] = consumer['uuid']

    done = 0
    for consumer in consumers:
        if (done % 10) == 0:
            _LOG.info("%s consumers uploaded so far." % done)
        if katello_client.findBySpacewalkID("satellite-%s" % consumer['owner'], consumer['id']):
            katello_client.updateConsumer(cp_uuid=names_to_uuids[consumer['name']],
                                          sw_id = consumer['id'],
                                          name = consumer['name'],
                                          facts=consumer['facts'],
                                          installed_products=consumer['installed_products'],
                                          owner=consumer['owner'],
                                          last_checkin=consumer['last_checkin'])
        else:
            uuid = katello_client.createConsumer(name=consumer['name'],
                                                sw_uuid=consumer['id'],
                                                facts=consumer['facts'],
                                                installed_products=consumer['installed_products'],
                                                last_checkin=consumer['last_checkin'],
                                                owner=consumer['owner'],
                                                spacewalk_server_hostname=CONFIG.get('spacewalk', 'host'))
        done += 1

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

    _LOG.info("calculating base channels from cloned channels")
    channel_map = channel_mapping(channels)
    for system in systems:
        system['software_channel'] = channel_map.get(
                                        system['software_channel'],
                                        system['software_channel'])


def spacewalk_sync(options):
    """
    Performs the data capture, translation and checkin to katello
    """
    _LOG.info("Started capturing system data from spacewalk")
    client = SpacewalkClient(CONFIG.get('spacewalk', 'host'),
                             CONFIG.get('spacewalk', 'ssh_key_path'))
    katello_client = KatelloConnection()
    consumers = []

    _LOG.info("retrieving data from spacewalk")
    sw_user_list = client.get_user_list()
    system_details = client.get_system_list()
    channel_details = client.get_channel_list()
    hosts_guests = client.get_host_guest_list()
    update_system_channel(system_details, channel_details)
    org_list = client.get_org_list()

    update_owners(katello_client, org_list)
    update_users(katello_client, sw_user_list)
    update_roles(katello_client, sw_user_list)

    katello_consumer_list = katello_client.getConsumers()
    delete_stale_consumers(katello_client, katello_consumer_list, system_details)

    _LOG.info("adding installed products to %s spacewalk records" % len(system_details))
    # enrich with engineering product IDs
    clone_mapping = []
    map(lambda details :
            details.update({'installed_products' : \
                            get_product_ids(details['software_channel'])}),
                           system_details)

    # convert the system details to katello consumers
    consumers.extend(transform_to_consumers(system_details))
    _LOG.info("found %s systems to upload into katello" % len(consumers))
    _LOG.info("uploading to katello...")
    upload_to_katello(consumers, katello_client)
    _LOG.info("upload completed")#. updating with guest info..")
#    consumer_list = katello_client.getConsumers(with_details=False)
#    upload_host_guest_mapping(consumer_list, katello_client)
#    _LOG.info("guest upload completed")


def splice_sync(options):
    """
    Syncs data from katello to splice
    """
    _LOG.info("Started syncing system data to splice")
    # now pull put out of katello, and into rcs!
    katello_consumers = get_katello_consumers()
    katello_client = KatelloConnection()
    _LOG.info("calculating marketing product usage")

    # create the base marketing usage list
    rcs_mkt_usage = map(transform_to_rcs, katello_consumers)

    # enrich with product usage info
    map(lambda rmu : 
            rmu.update(
                {'product_info': transform_entitlements_to_rcs(
                                    get_katello_entitlements(
                                        rmu['instance_identifier']))}), 
                                        rcs_mkt_usage)
    _LOG.info("uploading to splice...")
    upload_to_rcs(mpu_data=build_rcs_data(rcs_mkt_usage), sample_json=options.sample_json)
    _LOG.info("upload completed")


def main(options):

    global CONFIG
    CONFIG = utils.cfg_init(config_file=constants.SPLICE_CHECKIN_CONFIG)

    start_time = time.time()
    _LOG.info("run starting")

    socket.setdefaulttimeout(CONFIG.getfloat('main', 'socket_timeout'))

    if options.spacewalk_sync:
        spacewalk_sync(options)
    elif options.splice_sync:
        splice_sync(options)
    else:
        spacewalk_sync(options)
        splice_sync(options)

    finish_time = time.time() - start_time
    _LOG.info("run complete") 
