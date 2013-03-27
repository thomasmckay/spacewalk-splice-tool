#!/usr/bin/python
import sys
from rhsm.connection import UEPConnection
from datetime import datetime, timedelta
_LIBPATH = "/usr/share/rhsm"
# add to the path if need be
if _LIBPATH not in sys.path:
    sys.path.append(_LIBPATH)

from subscription_manager import logutil
from subscription_manager.certdirectory import CertificateDirectory
from rhsm.certificate import GMT

logutil.init_logger()

class CandlepinConnection():

    def getOwners(self):
        return self.cp.getOwnerList(self.username)

    def __init__(self):
        self.conn_username = "admin"
        self.owner = "admin"
        self.cp = UEPConnection(username=self.conn_username, password="admin",
                    host="localhost", ssl_port=8443,
                    handler="/candlepin", insecure=True)

    def createConsumer(self, name, facts, installed_products, last_checkin, uuid=None):
        consumer = self.cp.registerConsumer(name=name, facts=facts, owner=self.owner, installed_products=installed_products, uuid=uuid)
        print "created consumer with uuid %s. binding.." % consumer['uuid']
        self.cp.bind(consumer['uuid'], entitle_date=datetime.now())
        print "bind complete"
        self.cp.checkin(consumer['uuid'], self._convert_date(last_checkin))
        return consumer['uuid']

    def updateConsumer(self, uuid, facts, installed_products, last_checkin):
        self.cp.updateConsumer(uuid, facts=facts, installed_products=installed_products)
        self.cp.checkin(uuid, self._convert_date(last_checkin))

    def getConsumers(self, owner=None):
        if owner is None:
            owner = self.owner
        return self.cp.getConsumers(owner)

    def getConsumer(self, uuid):
        try:
            return self.cp.getConsumer(uuid)
        except:
            #TODO: only do this on a 404 from candlepin
            return None

    def getConsumerFacts(self, uuid=None):
        if uuid is None:
           raise Exception("no uuid provided") 
        return self.cp.getConsumer(uuid)['facts']

    def getEntitlements(self, uuid=None):
        if uuid is None:
           raise Exception("no uuid provided") 
        return self.cp.getEntitlementList(uuid)

    def _convert_date(self, dt):
        retval = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
        return retval

if __name__ == '__main__':

    facts =   {
        "cpu.core(s)_per_socket" : "1",
        "cpu.cpu(s)" : "1",
        "cpu.cpu_socket(s)" : "1",
        "distribution.id" : "Tikanga",
        "distribution.name" : "Red Hat Enterprise Linux Server",
        "distribution.version" : "5.9",
        "dmi.memory.size" : "1024 MB",
        "dmi.system.uuid" : "6882755d-2297-5f2d-219b-f33e59df959d",
        "memory.memtotal" : "1026120",
        "memory.swaptotal" : "2064376",
        "net.interface.eth0.ipv4_address" : "192.168.122.13",
        "net.interface.eth0.ipv4_broadcast" : "192.168.122.255",
        "net.interface.eth0.ipv4_netmask" : "24",
        "net.interface.eth0.mac_address" : "52:54:00:CD:2F:D6",
        "network.hostname" : "localhost.localdomain",
        "system.certificate_version" : "3.0",
        "uname.machine" : "x86_64",
        "uname.release" : "2.6.18-348.el5",
        "uname.sysname" : "Linux",
        "uname.version" : "#1 SMP Wed Nov 28 21:22:00 EST 2012",
        "virt.host_type" : "kvm",
        "virt.is_guest" : "true",
        "virt.uuid" : "6882755d-2297-5f2d-219b-f33e59df959d"
    }

    print "initializing connection"
    cc = CandlepinConnection()
    cc.cp.ping()
    cert_dir = CertificateDirectory("/usr/share/rhsm/product/RHEL-6/")
    product_cert = cert_dir.findByProduct("69")
    installed_products = [{"productId": product_cert.products[0].id, "productName": product_cert.products[0].name}]

    uuid = cc.createConsumer("foobar", facts, installed_products)
    print "updating"
    product_cert = cert_dir.findByProduct("83")
    installed_products = [{"productId": product_cert.products[0].id, "productName": product_cert.products[0].name}]
    cc.updateConsumer(uuid, facts, installed_products)

    print "done"




