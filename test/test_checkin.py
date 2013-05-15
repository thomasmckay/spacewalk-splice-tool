# -*- coding: utf-8 -*-
#
# Copyright © 2014 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.


from mock import Mock, patch
import socket

from base import SpliceToolTest

from spacewalk_splice_tool import checkin
from spacewalk_splice_tool import sw_client


class CheckinTest(SpliceToolTest):

    def setUp(self):
        super(CheckinTest, self).setUp()

    def test_main(self):
        mocked_sw_sync = self.mock(checkin, 'spacewalk_sync')
        mocked_splice_sync = self.mock(checkin, 'splice_sync')
        options = Mock()

        def reset():
            mocked_sw_sync.reset_mock()
            mocked_splice_sync.reset_mock()
            options.configure_mock(spacewalk_sync=False, splice_sync=False)

        options.spacwalk_sync = True
        checkin.main(options)
        self.assertTrue(mocked_sw_sync.called)
        self.assertFalse(mocked_splice_sync.called)
        reset()

        options.splice_sync = True
        checkin.main(options)
        self.assertFalse(mocked_sw_sync.called)
        self.assertTrue(mocked_splice_sync.called)
        reset()

        checkin.main(options)
        self.assertTrue(mocked_sw_sync.called)
        self.assertTrue(mocked_splice_sync.called)
        reset()

        self.assertEquals(socket.getdefaulttimeout(), 300)

    def test_spacewalk_sync(self):
        mocked_sw_client_class = self.mock(checkin, 'SpacewalkClient')
        mocked_sw_client = Mock()
        mocked_sw_client_class.return_value = mocked_sw_client
        mocked_cp_client_class = self.mock(checkin, 'KatelloConnection')
        mocked_cp_client = Mock()
        mocked_cp_client_class.return_value = mocked_cp_client

        mocked_sw_client.get_user_list.return_value = user_list
        mocked_sw_client.get_system_list.return_value = system_list
        mocked_sw_client.get_channel_list.return_value = channel_list
        mocked_sw_client.get_org_list.return_value = org_list

        mocked_cp_client.getOwners.return_value = owner_list
        mocked_cp_client.getRedhatProvider.return_value = provider
        mocked_cp_client.getRoles.return_value = role_list
        mocked_cp_client.getUsers.return_value = cp_user_list
        mocked_cp_client.getConsumers.return_value = consumer_list
        
        options = Mock()
        delete_stale_consumers = self.mock(checkin, 'delete_stale_consumers')
        upload_to_cp = self.mock(checkin, 'upload_to_katello')

        checkin.spacewalk_sync(options)

        # base channel was set to RH channel
        self.assertEquals('rhel-x86_64-server-6',
                          system_list[1]['software_channel'])
        self.assertTrue(delete_stale_consumers.called)
        self.assertTrue(system_list[0].has_key('installed_products'))
        self.assertTrue(system_list[1].has_key('installed_products'))
        self.assertTrue(upload_to_cp.called)
        self.assertEquals(2, len(upload_to_cp.call_args[0][0]))

    def test_host_guest_sync(self):
        mocked_cp_client = Mock()
        checkin.upload_host_guest_mapping(consumer_list, mocked_cp_client)


user_list = [{'username': 'admin', 
              'first_name': 'James', 
              'last_name': 'Slagle', 
              'user_id': '1', 
              'last_login_time': '2013-05-01 13:27:31', 
              'creation_time': '2013-04-25 08:28:08', 
              'organization_id': '1', 
              'role': 'Organization Administrator;Satellite Administrator', 
              'position': '', 
              'active': 'enabled', 
              'organization': 'Red Hat (Internal Use Only)', 
              'email': 'jslagle@redhat.com'}]

system_list = [{'memory': '7466', 
                'server_id': '1000010001', 
                'software_channel': 'rhel-x86_64-server-6', 
                'name': 'ec2-23-20-74-50.compute-1.amazonaws.com', 
                'registration_time': '2013-04-25 15:25:08', 
                'registered_by': 'admin', 
                'hostname': 'ec2-23-20-74-50.compute-1.amazonaws.com', 
                'org_id': '1', 
                'ipv6_address': '::1', 
                'hardware': '2 CPUs 1 Sockets; eth0 10.96.161.145/255.255.255.0 12:31:39:16:a2:67; lo 127.0.0.1/255.0.0.0 00:00:00:00:00:00', 
                'system_group': '', 
                'architecture': 'x86_64', 
                'virtual_host': '', 
                'last_checkin_time': '2013-04-25 15:25:34', 
                'entitlements': 'Spacewalk Management Entitled Servers', 
                'organization': 'Red Hat (Internal Use Only)', 
                'ip_address': '10.96.161.145', 
                'virtual_host': '1000010002', 
                'sockets': '1'}, 
               {'memory': '7466', 
                'server_id': '1000010002', 
                'software_channel': 'clone-clone-2-rhel-x86_64-server-6', 
                'name': 'ec2-23-20-74-50.compute-1.amazonaws.com', 
                'registration_time': '2013-04-25 15:51:03', 
                'registered_by': 'admin', 
                'hostname': 'ec2-23-20-74-50.compute-1.amazonaws.com', 
                'org_id': '1', 
                'ipv6_address': '::1', 
                'hardware': '2 CPUs 1 Sockets; eth0 10.96.161.145/255.255.255.0 12:31:39:16:a2:67; lo 127.0.0.1/255.0.0.0 00:00:00:00:00:00', 
                'system_group': '', 
                'architecture': 'x86_64', 
                'virtual_host': '', 
                'last_checkin_time': '2013-05-03 13:15:03', 
                'entitlements': 'Spacewalk Management Entitled Servers', 
                'organization': 'Red Hat (Internal Use Only)', 
                'ip_address': '10.96.161.145', 
                'sockets': '1'}
              ]

channel_list = [{'new_channel_label': 'clone-rhel-x86_64-server-6',
                 'new_channel_name': 'Clone of Red Hat Enterprise Linux Server (v. 6 for 64-bit x86_64)',
                 'original_channel_label': 'rhel-x86_64-server-6',
                 'original_channel_name': 'Red Hat Enterprise Linux Server (v. 6 for 64-bit x86_64)'},
                {'new_channel_label': 'clone-2-rhel-x86_64-server-6',
                 'new_channel_name': 'Clone 2 of Red Hat Enterprise Linux Server (v. 6 for 64-bit x86_64)',
                 'original_channel_label': 'rhel-x86_64-server-6',
                 'original_channel_name': 'Red Hat Enterprise Linux Server (v. 6 for 64-bit x86_64)'},
                {'new_channel_label': 'clone-clone-2-rhel-x86_64-server-6',
                 'new_channel_name': 'Clone of Clone 2 of Red Hat Enterprise Linux Server (v. 6 for 64-bit x86_64)',
                 'original_channel_label': 'clone-2-rhel-x86_64-server-6',
                 'original_channel_name': 'Clone 2 of Red Hat Enterprise Linux Server (v. 6 for 64-bit x86_64)'}]

org_list = {'1': 'Red Hat (Internal Use Only)'}

owner_list = \
    [{u'created_at': u'2013-05-01T21:33:43Z',
      u'default_info': {u'system': []},
      u'description': u'no description',
      u'id': 3,
      u'label': u'satellite-1',
      u'name': u'Red Hat (Internal Use Only)',
      u'service_levels': [u'None'],
      u'task_id': None,
      u'updated_at': u'2013-05-01T21:33:44Z'},
     {u'created_at': u'2013-04-24T20:10:51Z',
      u'default_info': {u'system': []},
      u'description': u'ACME_Corporation Organization',
      u'id': 1,
      u'label': u'ACME_Corporation',
      u'name': u'ACME_Corporation',
      u'service_levels': [],
      u'task_id': None,
      u'updated_at': u'2013-04-24T20:10:51Z'}]

cp_user_list = \
    [{u'created_at': u'2013-04-24T20:10:51Z',
      u'default_environment': None,
      u'default_environment_id': None,
      u'default_organization': None,
      u'disabled': False,
      u'email': u'root@localhost',
      u'foreman_id': None,
      u'helptips_enabled': True,
      u'hidden': False,
      u'id': 1,
      u'page_size': 25,
      u'password': u'asdf',
      u'password_reset_sent_at': None,
      u'password_reset_token': None,
      u'preferences': {},
      u'remote_id': u'admin',
      u'updated_at': u'2013-05-01T21:35:13Z',
      u'username': u'admin'}]

role_list = \
    [{u'created_at': u'2013-04-24T20:10:49Z',
      u'description': u'Super administrator with all access.',
      u'id': 1,
      u'locked': True,
      u'name': u'Administrator',
      u'updated_at': u'2013-04-24T20:10:50Z'},
     {u'created_at': u'2013-05-01T21:33:44Z',
      u'description': u'generated from spacewalk',
      u'id': 5,
      u'locked': False,
      u'name': u'Org Admin Role for satellite-1',
      u'updated_at': u'2013-05-01T21:33:44Z'},
     {u'created_at': u'2013-04-24T20:10:50Z',
      u'description': u'Read only role.',
      u'id': 2,
      u'locked': True,
      u'name': u'Read Everything',
      u'updated_at': u'2013-04-24T20:10:50Z'}]

provider = ''

consumer_list = \
    [{u'activation_key': [],
      u'content_view_id': None,
      u'created_at': u'2013-05-03T20:37:54Z',
      u'description': u'Initial Registration Params',
      u'environment': {u'created_at': u'2013-05-01T21:33:43Z',
                       u'description': u'',
                       u'id': 5,
                       u'label': u'spacewalk_environment',
                       u'library': False,
                       u'name': u'spacewalk_env',
                       u'organization': u'Red Hat (Internal Use Only)',
                       u'organization_id': 3,
                       u'prior': u'Library',
                       u'prior_id': 4,
                       u'updated_at': u'2013-05-01T21:33:43Z'},
      u'environment_id': 5,
      u'guests': [],
      u'id': 18,
      u'ipv4_address': None,
      u'location': u'None',
      u'name': u'ec2-23-20-74-50.compute-1.amazonaws.com',
      u'serviceLevel': u'',
      u'updated_at': u'2013-05-03T20:37:54Z',
      u'uuid': u'6b60e3e2-a614-4c20-b2c0-2e4cbfc821d1'},
     {u'activation_key': [],
      u'content_view_id': None,
      u'created_at': u'2013-05-03T20:37:56Z',
      u'description': u'Initial Registration Params',
      u'environment': {u'created_at': u'2013-05-01T21:33:43Z',
                       u'description': u'',
                       u'id': 5,
                       u'label': u'spacewalk_environment',
                       u'library': False,
                       u'name': u'spacewalk_env',
                       u'organization': u'Red Hat (Internal Use Only)',
                       u'organization_id': 3,
                       u'prior': u'Library',
                       u'prior_id': 4,
                       u'updated_at': u'2013-05-01T21:33:43Z'},
      u'environment_id': 5,
      u'guests': [],
      u'id': 19,
      u'ipv4_address': None,
      u'location': u'None',
      u'name': u'ec2-23-20-74-50.compute-1.amazonaws.com',
      u'serviceLevel': u'',
      u'updated_at': u'2013-05-03T20:37:56Z',
      u'uuid': u'f8e2e155-31f4-4e25-acbd-8eb951bd23ac'}]

