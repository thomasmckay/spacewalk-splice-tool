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
from katello.client.api.user import UserAPI
from katello.client.api.user_role import UserRoleAPI
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

class CandlepinConnection():

    def __init__(self):
        self.orgapi  = OrganizationAPI()
        self.systemapi  = SystemAPI()
        self.userapi  = UserAPI()
        self.envapi  = EnvironmentAPI()
        self.rolesapi  = UserRoleAPI()
        self.permissionapi  = PermissionAPI()
        # XXX: not sure yet how this works..
        s = server.KatelloServer('10.16.79.145', '443', 'https', '/katello')
        s.set_auth_method(BasicAuthentication('admin', 'admin'))
        server.set_active_server(s)


        CONSUMER_KEY = CONFIG.get("candlepin", "oauth_key")
        CONSUMER_SECRET = CONFIG.get("candlepin", "oauth_secret")
        # NOTE: callers must add leading slash when appending
        self.url = CONFIG.get("candlepin", "url")
        # Setup a standard HTTPSConnection object
        parsed_url = urlparse.urlparse(self.url)
        (hostname, port) = parsed_url[1].split(':')
        self.connection = httplib.HTTPSConnection(hostname, port)
        # Create an OAuth Consumer object 
        self.consumer = oauth.Consumer(CONSUMER_KEY, CONSUMER_SECRET)


    def _request(self, rest_method, request_method='GET', info=None, decode_json=True):

        raise Exception("SHOULD NOT BE HERE")
        # Formulate a OAuth request with the embedded consumer with key/secret pair
        if rest_method[0] != '/':
            raise Exception("rest_method must begin with a / char")

        full_url = self.url + rest_method

        if info:
            body = json.dumps(info)
        else:
            body = None
        
        oauth_request = oauth.Request.from_consumer_and_token(self.consumer, http_method=request_method, http_url=full_url)
        # Sign the Request.  This applies the HMAC-SHA1 hash algorithm
        oauth_request.sign_request(oauth.SignatureMethod_HMAC_SHA1(), self.consumer, None)

        headers = dict(oauth_request.to_header().items() + {'cp-user':'admin'}.items())
        auth = base64.encodestring( 'admin' + ':' + 'admin' )

        # Actually make the request
        #self.connection.request(request_method, full_url, headers=headers, body=body) 
        self.connection.request(request_method, full_url, headers={ 'Authorization' : 'Basic ' + auth }, body=body)
        # Get the response and read the output
        response = self.connection.getresponse()
        output = response.read()

        if response.status == 404:
            raise NotFoundException()
        if response.status not in [200, 204]:
            print output
            raise Exception("bad response code: %s" % response.status)

        if output:
            if decode_json:
                return json.loads(output)
            else:
                return output
        return None
        
    def getOwners(self):
        return self.orgapi.organizations()

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
        
    def checkin(self, uuid, checkin_date=None ):
        method = "/consumers/%s/checkin" % self._sanitize(uuid)
        # add the optional date to the url
        if checkin_date:
            method = "%s?checkin_date=%s" % (method,
                    self._sanitize(checkin_date.isoformat(), plus=True))
        return self._request(method, 'PUT')

    def createConsumer(self, name, facts, installed_products, last_checkin, uuid=None, owner=None):

        # two hacks: name should be name, and we should be able to pass installed products up as part of this
        consumer = self.systemapi.register(name=uuid, org='satellite-' + owner, environment_id=None,
                                            facts=facts, activation_keys=None, cp_type='system')

        returned = self.systemapi.update(consumer['uuid'], {'name': consumer['name'], 'installedProducts':installed_products})

        print "GOT BACK %s"  % returned

        # we need to bind and set lastCheckin time

        return consumer['uuid']
        

    
    def updateConsumer(self, cp_uuid, facts, installed_products, last_checkin, sw_id, owner=None, guest_uuids=None,
                        release=None, service_level=None):
        # XXX: need to support altering owner of existing consumer

        params = {}
        params['name'] = sw_id
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

        self.systemapi.update(cp_uuid, params)

        #self.checkin(uuid, self._convert_date(last_checkin))

    def getConsumers(self, owner=None):
        #url = '/consumers/'
        #if owner:
        #    method = "%s?owner=%s" % (method, owner)

        #return self._request(url, 'GET')

        # the API wants "orgId" but they mean "label"
        org_ids = map(lambda x: x['label'], self.orgapi.organizations())
        consumer_list = []
        for org_id in org_ids:
            consumer_list.append(self.systemapi.systems_by_org(orgId=org_id))
        
        # flatten the list
        return list(itertools.chain.from_iterable(consumer_list))

    def deleteConsumer(self, consumer_uuid):
        self.systemapi.unregister(consumer_uuid)
        # XXX: only for dev use
        self.systemapi.remove_consumer_deletion_record(consumer_uuid)

    def removeDeletionRecord(self, consumer_id):
        url = '/consumers/%s/deletionrecord'
        self._request(url % consumer_id, 'DELETE')

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

    def getEntitlements(self, uuid):
        url = "/consumers/%s/entitlements" % self._sanitize(uuid)
        return self._request(url, 'GET')

    def _convert_date(self, dt):
        retval = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
        return retval

    def _sanitize(self, urlParam, plus=False):
        #This is a wrapper around urllib.quote to avoid issues like the one
        #discussed in http://bugs.python.org/issue9301
        if plus:
            retStr = urllib.quote_plus(str(urlParam))
        else:
            retStr = urllib.quote(str(urlParam))
        return retStr

    def getRules(self):
        url = "/rules"
        encoded_rules = self._request(url, 'GET', decode_json=False)
        decoded_rules = base64.b64decode(encoded_rules)
        return Rules(version="0", data=decoded_rules)


    def getProducts(self):
        url = "/products"
        data = self._request(url, 'GET')
        return self.translateProducts(data)

    def getPools(self):
        url = "/pools"
        data = self._request(url, 'GET')
        return self.translatePools(data)

    def translateProducts(self, data):
        products = []
        for item in data:
            product = Product()
            product.updated = convert_to_datetime(item["updated"])
            if item.has_key("created"):
                product.created = convert_to_datetime(item["created"])
            else:
                # Candlepin has some 'products' which have an 'updated', but no 'created'
                _LOG.info("Product '%s' does not have a 'created' value, defaulting to value for updated" % (item["id"]))
                product.created = product.updated
 
            product.product_id = item["id"]
            product.name = item["name"]
            for attribute in item["attributes"]:
                # Expecting values for "type", "arch", "name"
                product.attrs[attribute["name"]] = attribute["value"]
            eng_prods = []
            eng_ids = []
            for prod_cnt in item["productContent"]:
                ep = dict()
                ep["id"] = prod_cnt["content"]["id"]
                ep["label"] = prod_cnt["content"]["label"]
                ep["name"] = prod_cnt["content"]["name"]
                ep["vendor"] = prod_cnt["content"]["vendor"]
                eng_prods.append(ep)
                eng_ids.append(ep["id"])
            product.eng_prods = eng_prods
            product.engineering_ids = eng_ids
            product.dependent_product_ids = item["dependentProductIds"]
            products.append(product)
        return products


    def translatePools(self, data):
        pools = []
        for item in data:
            p = Pool()
            p.uuid = item["id"]
            p.account = item["accountNumber"]
            p.created = convert_to_datetime(item["created"])
            p.quantity = item["quantity"]
            p.end_date = convert_to_datetime(item["endDate"])
            p.start_date = convert_to_datetime(item["startDate"])
            p.updated = convert_to_datetime(item["updated"])
            for prod_attr in item["productAttributes"]:
                name = prod_attr["name"]
                value = prod_attr["value"]
                p.product_attributes[name] = value
            p.product_id = item["productId"]
            p.product_name = item["productName"]
            provided_products = []
            for prov_prod in item["providedProducts"]:
                entry = dict()
                entry["id"] = prov_prod["productId"]
                entry["name"] = prov_prod["productName"]
                provided_products.append(entry)
            p.provided_products = provided_products
            pools.append(p)
        return pools

if __name__ == '__main__':
    cc = CandlepinConnection()
    print cc.getOwners()
    print cc.createOwner("foo", "foo name")
    print cc.deleteOwner("foo")
    print cc.getOwners()

    print cc.createConsumer("foo", {}, [], '2009-01-01 05:01:01', uuid="123", owner='admin')
    print cc.unregisterConsumers(["123"])
    print cc.removeDeletionRecord("123")

    print "Rules = %s" % (cc.getRules())
    print "Pools = %s" % (cc.getPools())
    print "Product = %s" % (cc.getProducts())


