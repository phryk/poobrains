import os
import re
import shutil
#import unittest
import pytest

import OpenSSL

import poobrains
from click.testing import CliRunner
    
ops = {
    'c': 'create',
    'r': 'read',
    'u': 'update',
    'd': 'delete'
}

@pytest.fixture
def client():

        poobrains.app.wsgi_app = FakeHTTPSMiddleware(poobrains.app.wsgi_app)
        poobrains.app.config['SECRET_KEY'] = 'fnord'
        poobrains.app.config['TESTING'] = True
        poobrains.app.debug = True
        client = poobrains.app.test_client()

        if not os.environ.has_key('FLASK_APP'):
            os.environ['FLASK_APP'] = '__main__'
        #poobrains.project_name = os.environ['FLASK_APP']


        yield client

        # Everything after yield is teardown? Is that right?


class FakeHTTPSMiddleware(object):

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):

        environ['wsgi.url_scheme'] = 'https'
        environ['SSL_CLIENT_VERIFY'] = 'FNORD'
        return self.app(environ, start_response)



def test_cli_install(client):

    input = """poobrains.local



poobrains@mail.local
mail.local
587
poobrains
poopass
root@mail.local



y
"""

    runner = CliRunner()
    rv = runner.invoke(poobrains.cli.install, input=input)
    print rv.output

    assert not rv.exception, rv.exception.message
    assert "Installation complete!" in rv.output, "Installation apparently didn't complete!"

    import config
    for name in dir(config):
        if name.isupper():
            poobrains.app.config[name] = getattr(config, name)

    client.get('/') # first request that triggers before_first_request to finish booting poobrains


def test_cert_page(client):

    rv = client.get('/cert/')
    assert rv.status_code == 200, "Expected status code 200 at /cert/, got %d" % rv.status_code


def test_redeem_token(client):

    token = poobrains.auth.ClientCertToken.get() # loads the token created by test_cli_install

    rv = client.post('/cert/', data={'ClientCertForm.token': token.token, 'submit': 'ClientCertForm.tls_submit'})

    passphrase_request = client.get('/cert/') # one more request, contains a flash() with passphrase
    match = re.search(u">The passphrase for this delicious bundle of crypto is &#39;(.+)&#39;<", passphrase_request.data)

    assert match, "Couldn't find passphrase flash!"

    passphrase = match.group(1)

    try:
       OpenSSL.crypto.load_pkcs12(rv.data, passphrase)
    except Exception:
        raise AssertionError("Couldn't load PKCS12 with passphrase '%s'" % passphrase)

# TODO: CRUD tests for ALL non-abstract Storables
def test_create_api(client):

    u = poobrains.auth.User.load('root')
    g = u.groups[0]
    cls = poobrains.auth.Page

    instance = cls()
    instance.owner = u
    instance.group = g
    instance.path = '/florp/'
    instance.title = "Florp"
    instance.content = "*florp*"

    assert instance.save(force_insert=True) > 0


def test_read(client):

    cls = poobrains.auth.Page

    instance = cls.load(1) # loads page created in previous test

    assert instance.content == '*florp*'


def test_update(client):

    cls = poobrains.auth.Page

    instance = cls.load(1)
    instance.content = '*not* florp'
    instance.save()

    del instance

    instance = cls.load(1)

    assert instance.content == '*not* florp'


def test_delete(client):

    cls = poobrains.auth.Page

    instance = cls.load(1)
    assert instance.delete() > 0


def test_ownedpermission_read_user_grant(client):

    u = poobrains.auth.User()
    u.name = 'test-grant'
    u.save(force_insert=True)

    cls = poobrains.auth.Page

    up = poobrains.auth.UserPermission()
    up.user = u
    up.permission = cls.permissions['read'].__name__
    up.access = 'grant'
    up.save(force_insert=True)

    u = poobrains.auth.User.load(u.name)

    instance = cls()
    instance.owner = u
    instance.path = '/test-grant/'
    instance.title = 'Test grant'
    instance.content = 'test'
    instance.save()

    instance = cls.get(cls.path == instance.path)

    try:
        instance.permissions['read'].check(u)
        instance.delete()
    except poobrains.auth.AccessDenied:
        instance.delete()
        raise AssertionError('User-asigned Permission check for "create" does not allow access!')


def test_ownedpermission_read_user_deny(client):

    u = poobrains.auth.User()
    u.name = 'test-deny'
    u.save(force_insert=True)

    cls = poobrains.auth.Page

    up = poobrains.auth.UserPermission()
    up.user = u
    up.permission = cls.permissions['read'].__name__
    up.access = 'deny'
    up.save(force_insert=True)

    u = poobrains.auth.User.load(u.name)

    instance = cls()
    instance.owner = u
    instance.path = '/test-deny/'
    instance.title = 'Test deny'
    instance.content = 'test'
    instance.save()

    instance = cls.get(cls.path == instance.path)

    with pytest.raises(poobrains.auth.AccessDenied):
        instance.permissions['read'].check(u)


def test_ownedpermission_read_user_instance(client):

    u = poobrains.auth.User()
    u.name = 'test-instance'
    u.save(force_insert=True)

    cls = poobrains.auth.Page

    up = poobrains.auth.UserPermission()
    up.user = u
    up.permission = cls.permissions['read'].__name__
    up.access = 'instance'
    up.save(force_insert=True)

    u = poobrains.auth.User.load(u.name)

    instance = cls()
    instance.owner = u
    instance.path = '/test-instance/'
    instance.title = 'Test instance'
    instance.content = 'test'
    instance.save()

    instance = cls.get(cls.path == instance.path)

    for op, name in ops.iteritems():

        instance.access = ''
        instance.save()
        instance = cls.get(cls.path == instance.path)

        with pytest.raises(poobrains.auth.AccessDenied, message="!!! FALSE NEGATIVE IN PERMISSION SYSTEM !!! User-assigned OwnedPermission check for '%s' with empty instance access failed!" % name):
            instance.permissions[name].check(u)

        instance.access = op
        instance.save()
        instance = cls.get(cls.path == instance.path)

        try:
            instance.permissions[name].check(u)
        except poobrains.auth.AccessDenied:
            raise AssertionError("User-assigned OwnedPermission check for '%s' with instance access '%s' does not allow access!" %(name, op))


def run_all():

    # kill any previous install
    try:
        shutil.rmtree(os.path.join(poobrains.app.site_path, 'gnupg'))
    except:
        pass

    try:
        os.unlink('config.py')
    except:
        pass

    try:
        os.unlink('%s.db' % poobrains.project_name)
    except:
        pass

    try:
        os.unlink('%s.ini' % poobrains.project_name)
    except:
        pass

    try:
        os.unlink('%s.nginx.conf' % poobrains.project_name)
    except:
        pass

    pytest.main([os.path.join(poobrains.app.poobrain_path, 'testing.py')])
