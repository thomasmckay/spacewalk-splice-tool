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

import sys

def translate_sw_facts_to_subsmgr(system_details):
    """
    translate spacewalk facts to subscription manager format
    @param system_details: system deatils returned from spacewalk server for a systemid
    @type system_details: {}
    @return facts dict representing subscription mamager facts data
    """
    facts = dict()
    facts['systemid'] = system_details['server_id']
    # leave this blank in the katello UI
    facts['distribution.name'] = ""
    facts.update(cpu_facts(system_details))
    facts.update(network_facts(system_details))
    facts.update(memory_facts(system_details))
    #facts.update(guest_facts(system_details))
    return facts


def cpu_facts(cpuinfo):
    """
    Translate the cpu facts from spacewalk server to subscription mgr format
    """
    # we set this to 1 by default so candlepin does not remove the field from
    # the facts list. This is needed so the fact can bubble through to RCS.
    cpu_socket_count = 1
    if cpuinfo.has_key("sockets") and len(cpuinfo['sockets']) > 0:
        cpu_socket_count = cpuinfo['sockets']

    cpu_count = 1
    if cpuinfo.has_key("hardware") and len(cpuinfo['hardware']) > 0:
        cpu_count = cpuinfo['hardware'].split(';')[0].split()[0]

    cpu_facts_dict = dict()

    # rules.js depends on uname.machine, not lscpu
    cpu_facts_dict['uname.machine'] = cpuinfo['architecture']
    cpu_facts_dict['lscpu.l1d_cache'] = ""
    cpu_facts_dict['lscpu.architecture'] = cpuinfo['architecture']
    cpu_facts_dict['lscpu.stepping'] = ""
    cpu_facts_dict['lscpu.cpu_mhz'] = ""
    cpu_facts_dict['lscpu.vendor_id'] = ""
    cpu_facts_dict['lscpu.cpu(s)'] = cpu_count
    cpu_facts_dict['cpu.cpu(s)'] = cpu_count
    cpu_facts_dict['lscpu.model'] = ""
    cpu_facts_dict['lscpu.on-line_cpu(s)_list'] = ""
    cpu_facts_dict['lscpu.byte_order'] = ""
    cpu_facts_dict['lscpu.cpu_socket(s)'] = cpu_socket_count
    cpu_facts_dict['lscpu.core(s)_per_socket'] = \
        int(cpu_count) / int(cpu_socket_count)
    cpu_facts_dict['lscpu.hypervisor_vendor'] = ""
    #cpu_facts_dict['lscpu.numa_node0_cpu(s)'] = ""
    cpu_facts_dict['lscpu.bogomips'] = ""
    #cpu_facts_dict['cpu.core(s)_per_socket'] = ""
    cpu_facts_dict['cpu.cpu_socket(s)'] = cpu_socket_count
    cpu_facts_dict['lscpu.virtualization_type'] = ""
    cpu_facts_dict['lscpu.cpu_family'] = ""
    #cpu_facts_dict['lscpu.numa_node(s)'] = ""
    cpu_facts_dict['lscpu.l1i_cache'] = ""
    cpu_facts_dict['lscpu.l2_cache'] = ""
    cpu_facts_dict['lscpu.l3_cache'] = ""
    #cpu_facts_dict['lscpu.thread(s)_per_core'] = ""
    cpu_facts_dict['lscpu.cpu_op-mode(s)'] = ""
    return cpu_facts_dict


def memory_facts(meminfo):
    """
    Translate memory info
    """
    mem_facts_dict = dict()
    if meminfo.has_key('memory') and len(meminfo['memory']) > 0:
        mem_facts_dict['memory.memtotal'] = int(meminfo['memory']) * 1024
    return mem_facts_dict


def network_facts(nwkinfo):
    """
    Translate network interface facts
    """
    nwk_facts_dict = dict()
    nwk_info_by_interface = {}

    network_info = nwkinfo['hardware'].split(';')[1:]
    for n in network_info:
        (iface, addrmask, hwaddr) = n.split()
        nwk_facts_dict['net.interface.' + iface + '.mac_address'] = hwaddr
        nwk_facts_dict['net.interface.' + iface + '.ipv4_address'] = addrmask.split('/')[0]
        nwk_facts_dict['net.interface.' + iface + '.netmask'] = addrmask.split('/')[1]
        
    nwk_facts_dict['net.ipv4_address'] = nwkinfo['ip_address']
    nwk_facts_dict['network.hostname'] = nwkinfo['hostname']

    return nwk_facts_dict


def guest_facts(guestinfo):
    guest_facts_dict = dict()
    if guestinfo.has_key('active_guest_info'):
        guest_facts_dict['active_guest_info'] = guestinfo['active_guest_info']
    return guest_facts_dict

def inactive_facts(details):
    inactive_facts_dict = dict()
    if details.has_key("inactive"):
        if details["inactive"].has_key("last_boot"):
            inactive_facts_dict["inactive_dot_last_boot"] = str(details["inactive"]["last_boot"])
        if details["inactive"].has_key("last_checkin"):
            inactive_facts_dict["inactive_dot_last_checkin"] = str(details["inactive"]["last_checkin"])
    return inactive_facts_dict

if __name__ == "__main__":
    sw_details_data = {'cpu_info': {'arch': 'x86_64',
               'cache': '6144 KB',
               'count': 1,
               'family': '6',
               'flags': 'fpu de tsc msr pae cx8 cmov pat clflush mmx fxsr sse sse2 ss ht syscall nx lm up rep_good aperfmperf unfair_spinlock pni ssse3 cx16 sse4_1 hypervisor lahf_lm xsaveopt dts',
               'mhz': '2659',
               'model': 'Intel(R) Xeon(R) CPU           E5430  @ 2.66GHz',
               'stepping': '10',
               'vendor': 'GenuineIntel'},
  'dmi_info': {'asset': '(chassis: ) (chassis: ) (board: ) (system: )',
               'board': '',
               'product': '',
               'system': '',
               'vendor': ''},
  'id': 1000010020,
  'last_checkin': '20121024T11:41:36',
  'name': 'ec2-184-72-80-101.compute-1.amazonaws.com',
  'network_devices': [{'broadcast': '10.209.211.255',
                       'hardware_address': '12:31:39:07:d1:a5',
                       'interface': 'eth0',
                       'ip': '10.209.210.83',
                       'ipv6': [{'address': 'fe80::1031:39ff:fe07:d1a5',
                                 'netmask': '64',
                                 'scope': 'link'}],
                       'module': 'vif',
                       'netmask': '255.255.254.0'},
                      {'broadcast': '0.0.0.0',
                       'hardware_address': '00:00:00:00:00:00',
                       'interface': 'lo',
                       'ip': '127.0.0.1',
                       'ipv6': [{'address': '::1',
                                 'netmask': '128',
                                 'scope': 'host'}],
                       'module': 'loopback',
                       'netmask': '255.0.0.0'}],
  'ram': 1655,
  'subscribed_channels': [{'channel_id': 101,
                           'channel_label': 'rhel-x86_64-server-6'}],
  'swap': 0}
    print translate_sw_facts_to_subsmgr(sw_details_data)
