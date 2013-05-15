#!/usr/bin/python
import base64
import logging
import sys
import itertools
import urllib
import urlparse
from rhsm.connection import UEPConnection, RestlibException
from datetime import datetime, timedelta
from dateutil.tz import tzutc
_LIBPATH = "/usr/share/rhsm"
# add to the path if need be
if _LIBPATH not in sys.path:
    sys.path.append(_LIBPATH)

from katello.client.api.organization import OrganizationAPI
from katello.client.api.environment import EnvironmentAPI
from katello.client.api.system import SystemAPI
from katello.client.api.permission import PermissionAPI
from katello.client.api.provider import ProviderAPI
from katello.client.api.user import UserAPI
from katello.client.api.distributor import DistributorAPI
from katello.client.api.user_role import UserRoleAPI
from katello.client.api.custom_info import CustomInfoAPI
from katello.client import server
from katello.client.server import BasicAuthentication, SSLAuthentication
from subscription_manager import logutil
from subscription_manager.certdirectory import CertificateDirectory
from rhsm.certificate import GMT
import oauth2 as oauth
import httplib
import logging
import base64
import json
from spacewalk_splice_tool import utils, constants
from splice.common.models import Product, Pool, Rules
from splice.common.utils import convert_to_datetime

_LOG = logging.getLogger(__name__)
CONFIG = utils.cfg_init(config_file=constants.SPLICE_CHECKIN_CONFIG)

logutil.init_logger()

class NotFoundException():
    pass

class KatelloConnection():

    def __init__(self):
        self.orgapi  = OrganizationAPI()
        self.systemapi  = SystemAPI()
        self.userapi  = UserAPI()
        self.envapi  = EnvironmentAPI()
        self.rolesapi  = UserRoleAPI()
        self.permissionapi  = PermissionAPI()
        self.distributorapi  = DistributorAPI()
        self.provapi  = ProviderAPI()
        self.infoapi  = CustomInfoAPI()
        s = server.KatelloServer(CONFIG.get("katello", "hostname"),
                                 CONFIG.get("katello", "port"),
                                 'https',
                                 CONFIG.get("katello", "api_url"))
        s.set_auth_method(BasicAuthentication(CONFIG.get("katello", "admin_user"), CONFIG.get("katello", "admin_pass")))
        server.set_active_server(s)


    def getOwners(self):
        return self.orgapi.organizations()

    def createDistributor(self, name, root_org):
        return self.distributorapi.create(name=name, org=root_org, environment_id=None)

    def exportManifest(self, dist_uuid):
        return self.distributorapi.export_manifest(distributor_uuid = dist_uuid)

    def importManifest(self, prov_id, file):
        return self.provapi.import_manifest(provId=prov_id, manifestFile = file)

    def getRedhatProvider(self, org):
        return self.provapi.provider_by_name(orgName=org, provName="Red Hat")

    def getEntitlements(self, system_id):
        return self.systemapi.subscriptions(system_id=system_id)['entitlements']

    def getSubscriptionStatus(self, system_uuid):
        return self.systemapi.subscription_status(system_id=system_uuid)

    def createOwner(self, label, name):
        org = self.orgapi.create(name, label, "no description")
        library = self.envapi.library_by_org(org['label'])
        self.envapi.create(org['label'], "spacewalk_env", "spacewalk_environment", '', library['id'])
        return org

    def deleteOwner(self, name):
        # todo: error handling, not sure if orgapi will handle it
        self.orgapi.delete(name)

    def getUsers(self):
        return self.userapi.users()

    def createUser(self, username, email):
        return self.userapi.create(name=username, pw="CHANGEME", email=email, disabled=False, default_environment=None)

    def deleteUser(self, user_id):
        return self.userapi.delete(user_id=user_id)

    def findBySpacewalkID(self, org, spacewalk_id):
        result = self.systemapi.find_by_custom_info(org, 'spacewalk-id', spacewalk_id)
        if len(result) > 1:
            raise Exception("more than one record found for spacewalk ID %s in org %s!" % (spacewalk_id, org))

        return result
        
    def createConsumer(self, name, facts, installed_products, last_checkin,
                        sw_uuid=None, owner=None, spacewalk_server_hostname = None):

        # there are six calls here! we need to work with katello to send all this stuff up at once
        consumer = self.systemapi.register(name=name, org='satellite-' + owner, environment_id=None,
                                            facts=facts, activation_keys=None, cp_type='system')

        returned = self.systemapi.update(consumer['uuid'], {'name': consumer['name'], 'installedProducts':installed_products})

        self.systemapi.checkin(consumer['uuid'], self._convert_date(last_checkin))
        self.systemapi.refresh_subscriptions(consumer['uuid'])

        self.infoapi.add_custom_info(informable_type='system', informable_id=returned['id'],
                                        keyname='spacewalk-id', value=sw_uuid) 

        return consumer['uuid']
        

    
    def updateConsumer(self, name, cp_uuid, facts, installed_products, last_checkin, sw_id, owner=None, guest_uuids=None,
                        release=None, service_level=None):
        params = {}
        params['name'] = name
        if installed_products is not None:
            params['installedProducts'] = installed_products
        if guest_uuids is not None:
            params['guestIds'] = guest_uuids
        if facts is not None:
            params['facts'] = facts
        if release is not None:
            params['releaseVer'] = release
        if service_level is not None:
            params['serviceLevel'] = service_level

        # three rest calls, just one would be better
        self.systemapi.update(cp_uuid, params)
        self.systemapi.checkin(cp_uuid, self._convert_date(last_checkin))
        self.systemapi.refresh_subscriptions(cp_uuid)

    def getConsumers(self, owner=None, with_details=True):
        # TODO: this has a lot of logic and could be refactored
        
        # the API wants "orgId" but they mean "label"
        org_ids = map(lambda x: x['label'], self.orgapi.organizations())
        consumer_list = []
        for org_id in org_ids:
            consumer_list.append(self.systemapi.systems_by_org(orgId=org_id))
        
        # flatten the list
        consumer_list = list(itertools.chain.from_iterable(consumer_list))
        # return what we have, if we don't need the detailed list
        if not with_details:
            return consumer_list

        full_consumers_list = []
        # unfortunately, we need to call again to get the "full" consumer with facts
        for consumer in consumer_list:
            full_consumer = self._getConsumer(consumer['uuid'])
            full_consumer['entitlement_status'] = self.getSubscriptionStatus(consumer['uuid'])
            full_consumers_list.append(full_consumer)

        return full_consumers_list
    

    def _getConsumer(self, consumer_uuid):
        return self.systemapi.system(system_id=consumer_uuid)

    def deleteConsumer(self, consumer_uuid):
        self.systemapi.unregister(consumer_uuid)
        # XXX: only for dev use
        self.systemapi.remove_consumer_deletion_record(consumer_uuid)

    def getRoles(self, user_id = None):
        if user_id:
            return self.userapi.roles(user_id=user_id)
        else:
            return self.rolesapi.roles()

    def createOrgAdminRolePermission(self, kt_org_label):
        role = self.rolesapi.create(name="Org Admin Role for %s" % kt_org_label, description="generated from spacewalk")
        perm = self.permissionapi.create(roleId = role['id'], name = "Org Admin Permission for %s" % kt_org_label,
                                         description="generated from spacewalk", type_in="organizations", verbs=None,
                                         tagIds=None, orgId=kt_org_label, all_tags=True, all_verbs=True)

    def grantOrgAdmin(self, kt_user, kt_org_label):
        oa_role = self.rolesapi.role_by_name(name="Org Admin Role for %s" % kt_org_label)
        self.userapi.assign_role(user_id=kt_user['id'], role_id=oa_role['id'])

    def ungrantOrgAdmin(self, kt_user, kt_org_label):
        oa_role = self.rolesapi.role_by_name(name="Org Admin Role for %s" % kt_org_label)
        self.userapi.unassign_role(user_id=kt_user['id'], role_id=oa_role['id'])

    def grantFullAdmin(self, kt_user):
        admin_role = self.rolesapi.role_by_name(name="Administrator")
        self.userapi.assign_role(user_id=kt_user['id'], role_id=admin_role['id'])

    def ungrantFullAdmin(self, kt_user, kt_org_label):
        admin_role = self.rolesapi.role_by_name(name="Administrator")
        self.userapi.unassign_role(user_id=kt_user['id'], role_id=admin_role['id'])

    def _convert_date(self, dt):
        retval = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
        return retval

if __name__ == '__main__':
    kc = KatelloConnection()
    print kc.getOwners()
    print kc.createOwner("foo", "foo name")
    print kc.deleteOwner("foo")
    print kc.getOwners()

    print kc.createConsumer("foo", {}, [], '2009-01-01 05:01:01', uuid="123", owner='admin')
    print kc.unregisterConsumers(["123"])
    print kc.removeDeletionRecord("123")

    print "Rules = %s" % (kc.getRules())
    print "Pools = %s" % (kc.getPools())
    print "Product = %s" % (kc.getProducts())


