
from optparse import OptionParser
import sys
import os
import random
import string
import urlparse
from multiprocessing import Process, BoundedSemaphore, Manager
from multiprocessing import Pool
from subprocess import call

try:
    from katello.client import server
    from katello.client.server import BasicAuthentication, SSLAuthentication
    from katello.client.api.system import SystemAPI
    from katello.client.api.environment import EnvironmentAPI
    from katello.client.api.organization import OrganizationAPI
    from katello.client.api.user import UserAPI
    from katello.client.api.user_role import UserRoleAPI
    from katello.client.api.permission import PermissionAPI
    from katello.client.api.provider import ProviderAPI
    from katello.client.api.distributor import DistributorAPI
except ImportError, e:
    sys.stderr.write("[Error] %s\n, 'pip-python install katello-cli' is required\n" % e)
    sys.exit(-1)


def random_string():
    """
    Generates a random *alphanumeric* string between 4 and 6 characters
    in length.
    """
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for x in range(random.randint(4, 6)))


def init_api():
    global orgapi, userapi, roleapi, permapi, provapi, envapi, distapi

    orgapi  = OrganizationAPI()
    userapi = UserAPI()
    roleapi = UserRoleAPI()
    permapi = PermissionAPI()
    provapi = ProviderAPI()
    envapi  = EnvironmentAPI()
    distapi = DistributorAPI()


def parse_server(url):
    """
    Parse the url passed in to obtain host, protocol, port, and path.
    :param url: string
    """
    p_url = urlparse.urlparse(url)
    proto = p_url.scheme
    host = p_url.netloc
    path = p_url.path


    if ':' in host and (proto == 'https' or proto == 'http'):
        host, port = host.split(':')
    elif proto == 'https':
        port = 443
    elif proto == 'http':
        port = 80
    else:
        sys.stderr.write('[Error] Supported protocols are https or http\n')
        sys.exit(-1)

    return(proto,host,path,port)


def init_server():
    proto, host, path, port = parse_server(opts.url)
    s = server.KatelloServer(host, port, proto, path)
    s.set_auth_method(BasicAuthentication(opts.username, opts.password))
    server.set_active_server(s)


def get_or_create_org(name, label, description="No description"):
    global orgapi

    try:
        org = orgapi.organization(name)
        if opts.verbose:
            print "[Info] Organization '%s' exists" % name
    except server.ServerRequestError, e:
        if e[1]['displayMessage'] != "Couldn't find organization '%s'" % name:
            raise(e)
        org = orgapi.create(name, label, description)
        print "[Info] Created organization '%s'" % name

    return org


def setup_orgs():
    global mega_org, rnd_org

    mega_org = get_or_create_org("Mega Corporation", "Mega_Corp")
    rnd_org  = get_or_create_org("R&D Engineering", "Engineering")

    return [mega_org, rnd_org]


def get_or_create_user(name, pw="admin", email="foo@bar.com"):
    global userapi

    user = userapi.user_by_name(name)
    if user is not None:
        if opts.verbose:
            print "[Info] User '%s' exists" % name
    else:
        user = userapi.create(name, pw, email, False, None)
        print "[Info] Created user '%s'" % name

    return user


def setup_users():
    global mega_user, engineer_user

    mega_user     = get_or_create_user("mega")
    engineer_user = get_or_create_user("engineer-manager")
    engineer_user = get_or_create_user("engineer")


def get_or_create_role(name, description="No description"):
    global roleapi

    role = roleapi.role_by_name(name)
    if role is not None:
        if opts.verbose:
            print "[Info] Role '%s' exists" % name
    else:
        role = roleapi.create(name, description)
        print "[Info] Created role '%s'" % name

    return role


def get_or_create_permission(role, name):
    global permapi

    perm = permapi.permission_by_name(role['id'], name)
    if perm is not None:
        if opts.verbose:
            print "[Info] Permission '%s' exists" % name
    else:
        description = "No description"
        permission = permapi.create(role['id'], name, description, 'all', [], [], None, True)
        print "[Info] Created permisson '%s'" % name

    return perm


def setup_permissions():
    global mega_perm, rnd_perm

    mega_role = get_or_create_role("Mega Manager")
    mega_perm = get_or_create_permission(mega_role, "Mega Manager")

    rnd_role  = get_or_create_role("Engineering")
    rnd_perm  = get_or_create_permission(rnd_role, "Engineering")

    rnd_role  = get_or_create_role("Engineering Manager")
    rnd_perm  = get_or_create_permission(rnd_role, "Engineering Manager")


def setup_mega():
    global mega_org

    # Import manifest
    #
    redhat_prov = provapi.provider_by_name(mega_org['name'], 'Red Hat')
    manifest = './mega-manifest.zip'
    f = open(manifest)
    try:
        provapi.import_manifest(redhat_prov['id'], f)

        # For demo purposes hack the candlepin db to increase subscription quantity
        #rtn = os.system("/usr/bin/psql -U candlepin -c 'UPDATE cp_pool SET quantity=800;'")
        #if opts.verbose:
        #    print "[Info] Overwrote candlepin pool quantity"

        if opts.verbose:
            print "[Info] Manifest '%s' imported" % manifest
    except server.ServerRequestError, e:
        if e[1]['displayMessage'] == 'Import is the same as existing data':
            if opts.verbose:
                print "[Info] Manifest '%s' already imported" % manifest
        else:
            raise(e)
    finally:
        f.close

    # Environments
    #
    environment_name = 'Divisions'
    library = envapi.library_by_org(mega_org['label'])
    try:
        env = envapi.create(mega_org['label'], environment_name, environment_name, '', library['id'])
        if opts.verbose:
            print "[Info] %s environment '%s' created" % (mega_org['name'], environment_name)
    except server.ServerRequestError, e:
        if e[0] == 422:
            env = envapi.environment_by_name(mega_org['label'], environment_name)
            if opts.verbose:
                print "[Info] %s environment '%s' exists" % (mega_org['name'], environment_name)
        else:
            raise(e)

    # Distributors
    #
    distributor_name = 'Engineering'
    try:
        distapi.create(distributor_name, mega_org['name'], env['id'])
        if opts.verbose:
            print "[Info] %s distributor '%s' created" % (mega_org['name'], distributor_name)
    except server.ServerRequestError, e:
        if e[0] == 422:
            env = distapi.distributor_by_name(mega_org['label'], distributor_name)
            if opts.verbose:
                print "[Info] %s distributor '%s' exists" % (mega_org['name'], 'Divisions')
        else:
            raise(e)

    return


# main
#
if __name__ == '__main__':
    p = OptionParser(usage="usage: %prog [options]", version="%prog 0.01")
    p.add_option('--url', dest='url', help='Fully qualified url for your katello server',
                 default='localhost')
    p.add_option('-u', '--user', dest='username',
            help='Username, default = admin', default='admin')
    p.add_option('-p', '--password', dest='password',
            help='Password, default = admin', default='admin')
    p.add_option('-v', '--verbose', action='store_true', dest='verbose',
                 help='Enable Verbose Output', default=False)

    (opts, args) = p.parse_args()

    init_server()
    init_api()

    setup_orgs()
    setup_users()
    setup_permissions()
    setup_mega()
