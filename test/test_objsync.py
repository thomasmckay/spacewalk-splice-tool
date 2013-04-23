from spacewalk_splice_tool import checkin
from spacewalk_splice_tool.cpin_connect import CandlepinConnection
from mock import Mock


class TestObjectSync:
    def setUp(self):
        cp_orgs = [
                   {'name': 'bar org', 'label': 'satellite-2', 'id': 9, 'description': 'no description'},
                   {'name': 'foo org', 'label': 'satellite-1', 'id': 7, 'description': 'no description'},
                  ]
        self.cp_client = Mock()
        self.cp_client.createOwner = Mock()
        self.cp_client.deleteOwner = Mock()
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
