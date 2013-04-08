#!/usr/bin/python
import sys
import urllib
from rhsm.connection import UEPConnection, RestlibException
from datetime import datetime, timedelta
_LIBPATH = "/usr/share/rhsm"
# add to the path if need be
if _LIBPATH not in sys.path:
    sys.path.append(_LIBPATH)

from subscription_manager import logutil
from subscription_manager.certdirectory import CertificateDirectory
from rhsm.certificate import GMT
import oauth2 as oauth
import httplib
import json

logutil.init_logger()

class NotFoundException():
    pass

class CandlepinConnection():

    def __init__(self):
        CONSUMER_KEY = 'sst'
        CONSUMER_SECRET = 'sstsstsst'
        # NOTE: callers must add leading slash when appending
        self.url = "https://ec2-23-22-20-237.compute-1.amazonaws.com:8443/candlepin"
        # Setup a standard HTTPSConnection object
        self.connection = httplib.HTTPSConnection("ec2-23-22-20-237.compute-1.amazonaws.com", "8443")
        # Create an OAuth Consumer object 
        self.consumer = oauth.Consumer(CONSUMER_KEY, CONSUMER_SECRET)


    def _request(self, rest_method, request_method='GET', info=None):
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

        # Actually make the request
        self.connection.request(request_method, full_url, headers=headers, body=body) 
        # Get the response and read the output
        response = self.connection.getresponse()
        output = response.read()

        if response.status == 404:
            raise NotFoundException()
        if response.status not in [200, 204]:
            raise Exception("bad response code: %s" % response.status)

        if output:
            return json.loads(output)
        return None
        
    def getOwners(self):
        return self._request('/owners', 'GET')

    def createOwner(self, key, name):
        params = {"key": key}
        if name:
            params['displayName'] = name
        return self._request('/owners', 'POST', info=params)

    def deleteOwner(self, key):
        return self._request("/owners/%s" % key, 'DELETE')

    def checkin(self, uuid, checkin_date=None ):
        method = "/consumers/%s/checkin" % self._sanitize(uuid)
        # add the optional date to the url
        if checkin_date:
            method = "%s?checkin_date=%s" % (method,
                    self._sanitize(checkin_date.isoformat(), plus=True))

    def createConsumer(self, name, facts, installed_products, last_checkin, uuid=None, owner=None):
        info = {"type": 'system',
                  "name": name,
                  "facts": facts}
        if installed_products:
            info['installedProducts'] = installed_products

        if uuid:
            info['uuid'] = uuid

        url = "/consumers"

        if owner:
            query_param = urllib.urlencode({"owner": owner})
            url += "?%s" % query_param

        # create the consumer
        consumer = self._request(url, 'POST', info)

        print consumer

        # now do a bind
        url = "/consumers/%s/entitlements" % consumer['uuid']
        self._request(url, 'POST')

        # update the last checkin time
        self.checkin(consumer['uuid'], self._convert_date(last_checkin))

        return consumer['uuid']
        

    
    def updateConsumer(self, uuid, facts, installed_products, last_checkin, owner=None, guest_uuids=None,
                        release=None, service_level=None):
        # XXX: need to support altering owner of existing consumer
        params = {}
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

        url = "/consumers/%s" % self._sanitize(uuid)
        self._request(url, 'PUT', info=params)
        self.checkin(uuid, self._convert_date(last_checkin))

    def getConsumers(self, owner=None):
        url = '/consumers/'
        if owner:
            method = "%s?owner=%s" % (method, owner)

        return self._request(url, 'GET')

    def unregisterConsumers(self, consumer_id_list):
        url = '/consumers/%s'
        # we might change to to a bulk delete later
        # TODO: return something relevant
        for consumer_id in consumer_id_list:
            self._request(url % consumer_id, 'DELETE')

    def removeDeletionRecord(self, consumer_id):
        url = '/consumers/%s/deletionrecord'
        self._request(url % consumer_id, 'DELETE')
    

    def getConsumer(self, uuid):
        url = "/consumers/%s" % self._sanitize(uuid)
        return self._request(url, 'GET')

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


if __name__ == '__main__':
    cc = CandlepinConnection()
    print cc.getOwners()
    print cc.createOwner("foo", "foo name")
    print cc.deleteOwner("foo")
    print cc.getOwners()

    print cc.createConsumer("foo", {}, [], '2009-01-01 05:01:01', uuid="123", owner='admin')
    print cc.unregisterConsumers(["123"])
    print cc.removeDeletionRecord("123")
