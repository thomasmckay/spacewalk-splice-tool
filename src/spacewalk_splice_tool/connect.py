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

import base64
import simplejson as json
from M2Crypto import SSL, httpslib

class BaseConnection(object):
    def __init__(self, host, port, handler, username=None,
                 password=None, cert_file=None, key_file=None, ca_cert=None):
        self.host = host
        self.port = port
        self.handler = handler
        self.headers = {"Content-type":"application/json",
                        "Accept": "application/json"}
        self.username = username
        self.password = password
        self.cert_file = cert_file
        self.cert_key = key_file
        self.ca_cert  = ca_cert

    def set_basic_auth(self):
        encoded = base64.b64decode(':'.join((self.username, self.password)))
        basic = 'Basic %s' % encoded
        self.headers['Authorization'] = basic

    def set_ssl_context(self):
        context = SSL.Context("tlsv1")
        context.set_verify(SSL.verify_fail_if_no_peer_cert, 1)
        if self.ca_cert:
            context.load_verify_info(self.ca_cert)
        if self.cert_file:
            context.load_cert(self.cert_file, keyfile=self.cert_key)
        return context

    def _request(self, request_type, method, body=None):
        if self.username and self.password:
            # add the basic auth info to headers
            self.set_basic_auth()
        # initialize a context for ssl connection
        context = self.set_ssl_context()
        # ssl connection
        conn = httpslib.HTTPSConnection(self.host, self.port, ssl_context=context)
        conn.request(request_type, self.handler + method, body=json.dumps(body), headers=self.headers)
        response = conn.getresponse()
        if response.status not in [200, 202]:
            raise
        data = response.read()
        if not len(data):
            return None
        return json.loads(data)

    def GET(self, method):
        return self._request("GET", method)

    def POST(self, method, params=""):
        return self._request("POST", method, params)
