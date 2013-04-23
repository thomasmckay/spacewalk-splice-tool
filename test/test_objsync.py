from spacewalk_splice_tool import checkin
from spacewalk_splice_tool.cpin_connect import CandlepinConnection
from mock import Mock, call


class TestObjectSync:
    def setUp(self):
        cp_orgs = [
                   {'name': 'bar org', 'label': 'satellite-2',   'id': '9',   'description': 'no description'},
                   {'name': 'foo org', 'label': 'satellite-1',   'id': '7',   'description': 'no description'},
                   {'name': 'foo org', 'label': 'NOT-A-SAT-ORG', 'id': '100', 'description': 'no description'},
                  ]
        self.cp_client = Mock()
        self.cp_client.createOwner = Mock()
        self.cp_client.deleteOwner = Mock()
        self.cp_client.deleteConsumer = Mock()
        self.cp_client.getOwners = Mock(return_value=cp_orgs)

    def test_owner_add(self):
        sw_orgs = {'1': 'foo', '2': 'bar', '3': 'baz'}
        checkin.update_owners(self.cp_client, sw_orgs)
        self.cp_client.createOwner.assert_called_once_with(name='baz', label='satellite-3')

    def test_owner_delete(self):
        # owner #2 is missing and should get zapped 
        sw_orgs = {'1': 'foo', '3': 'baz'}
        checkin.update_owners(self.cp_client, sw_orgs)
        self.cp_client.deleteOwner.assert_called_once_with(name='bar org')

    def test_owner_noop(self):
        sw_orgs = {'1': 'foo', '2': 'bar'}
        checkin.update_owners(self.cp_client, sw_orgs)
        assert not self.cp_client.deleteOwner.called
        assert not self.cp_client.createOwner.called

    def test_system_remove(self):
        sw_system_list = [
                            { 'server_id': '100' },
                            { 'server_id': '101' },
                         ]

        kt_consumer_list = [
                            { 'name': '100', 'uuid': '1-1-1', 'environment': {'organization_id': '9'}},
                            { 'name': '101', 'uuid': '1-1-2', 'environment': {'organization_id': '7'}},
                            { 'name': '102', 'uuid': '1-1-3', 'environment': {'organization_id': '9'}},
                            { 'name': '102', 'uuid': '1-1-4', 'environment': {'organization_id': '100'}},
                            { 'name': '107', 'uuid': '1-1-5', 'environment': {'organization_id': '9'}},
                         ]
        checkin.delete_stale_consumers(self.cp_client, kt_consumer_list, sw_system_list)
        expected = [call('1-1-3'), call('1-1-5')]
        result = self.cp_client.deleteConsumer.call_args_list
        assert result == expected, "%s does not match expected call set %s" % (result, expected)
