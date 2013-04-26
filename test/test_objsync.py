from spacewalk_splice_tool import checkin
from spacewalk_splice_tool.cpin_connect import CandlepinConnection
from mock import Mock, call


class TestObjectSync:
    class Matcher(object):
        def __init__(self, compare, some_obj):
            self.compare = compare
            self.some_obj = some_obj
        def __eq__(self, other):
            return self.compare(self.some_obj, other)

    def user_compare(self, obj1, obj2):
        if obj1['username'] == obj2['username']:
            return True
        return False

    def setUp(self):

        cp_orgs = [
                   {'name': 'bar org', 'label': 'satellite-2',   'id': '9',   'description': 'no description'},
                   {'name': 'foo org', 'label': 'satellite-1',   'id': '7',   'description': 'no description'},
                   {'name': 'foo org', 'label': 'NOT-A-SAT-ORG', 'id': '100', 'description': 'no description'},
                  ]

        kt_userlist = [{'username': 'admin', 'id': 1, 'email': 'admin@foo.com'},
                        {'username': 'bazbaz', 'id': 3, 'email': 'bazbaz@foo.com'},
                        {'username': 'foo', 'id': 2, 'email': 'bazbaz@foo.com'}]

        kt_roles_for_org_admin = [{ 'id': 5, 'name': 'Org Admin Role for satellite-1'}]
        kt_roles_for_full_admin = [{ 'id': 5, 'name': 'Org Admin Role for satellite-1'},
                                   { 'id': 6, 'name': 'Administrator'}]

        def return_role(*args, **kwargs):
            # user id 2 in the katello test data set is foo
            if kwargs['user_id'] == 2:
                return []
            # user id 3 in the katello test data set is bazbaz
            if kwargs['user_id'] == 3:
                return kt_roles_for_full_admin
            return kt_roles_for_org_admin

        self.cp_client = Mock()
        self.cp_client.createOwner = Mock()
        self.cp_client.deleteOwner = Mock()
        # careful! this always returns the same mock username
        self.cp_client.createUser = Mock(return_value={'username': 'mockuser', 'id':'999'})
        self.cp_client.deleteConsumer = Mock()
        self.cp_client.getOwners = Mock(return_value=cp_orgs)
        self.cp_client.getUsers = Mock(return_value=kt_userlist)
        self.cp_client.createOrgAdminRolePermission = Mock()
        self.cp_client.getRoles = Mock(side_effect=return_role)

    def test_owner_add(self):
        sw_orgs = {'1': 'foo', '2': 'bar', '3': 'baz'}
        checkin.update_owners(self.cp_client, sw_orgs)
        self.cp_client.createOwner.assert_called_once_with(name='baz', label='satellite-3')
        self.cp_client.createOrgAdminRolePermission.assert_called_once_with(kt_org_label='satellite-3')

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

    def test_user_add(self):
        sw_userlist = [{'username': 'foo', 'user_id': '1',
                        'organization_id': '1', 'role': 'Organization Administrator;Satellite Administrator',
                        'organization': 'Awesome Org', 'email': 'foo@bar.com'},
                        {'username': 'barbar', 'user_id': '2',
                        'organization_id': '2', 'role': 'Organization Administrator', 'organization': 'foo org',
                        'email': 'bar@foo.com'}]

        checkin.update_users(self.cp_client, sw_userlist)
        expected = [call(username='barbar', email='bar@foo.com')]
        result = self.cp_client.createUser.call_args_list
        assert result == expected, "%s does not match expected call set %s" % (result, expected)

    def test_role_update(self):
        sw_userlist = [{'username': 'foo', 'user_id': '1', 'organization_id': '1',
                        'role': 'Organization Administrator;Satellite Administrator',
                        'organization': 'Awesome Org', 'email': 'foo@bar.com'},
                        {'username': 'barbar', 'user_id': '2', 'organization_id': '2',
                        'role': 'Organization Administrator', 'organization': 'foo org',
                        'email': 'bar@foo.com'},
                        {'username': 'bazbaz', 'user_id': '3', 'organization_id': '1',
                        'role': '', 'organization': 'foo org', 'email': 'baz@foo.com'}]
        checkin.update_roles(self.cp_client, sw_userlist)

        # user "foo" is an org admin on sat org 1, and needs to get added to
        # satellite-1 in katello
        user_matcher = TestObjectSync.Matcher(self.user_compare, {'username': 'foo'})
        expected = [call(kt_user=user_matcher, kt_org_label='satellite-1')]
        result = self.cp_client.grantOrgAdmin.call_args_list
        assert result == expected, "%s does not match expected call set %s" % (result, expected)

        # ensure user "foo" became a full admin
        self.cp_client.grantFullAdmin.assert_called_once_with(kt_user=user_matcher)

        # user "bazbaz" is not an org admin on sat org 1, and needs to get removed from
        # satellite-1 in katello
        user_matcher = TestObjectSync.Matcher(self.user_compare, {'username': 'bazbaz'})
        expected = [call(kt_user=user_matcher, kt_org_label='satellite-1')]
        result = self.cp_client.ungrantOrgAdmin.call_args_list
        assert result == expected, "%s does not match expected call set %s" % (result, expected)

        # ensure user "bazbaz" had full admin rights revoked 
        self.cp_client.ungrantFullAdmin.assert_called_once_with(kt_user=user_matcher)
        
