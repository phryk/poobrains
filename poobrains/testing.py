import os
import re
import shutil
import pytest

import random
import datetime

import OpenSSL

import poobrains
from click.testing import CliRunner

# helpers

def generate_int():

    return 42


def generate_float():

    return 5.55


generators = {
    int: generate_int,
    float: generate_float,
    str: poobrains.helpers.random_string_light,
    datetime.datetime: datetime.datetime.now
}

fieldmap = { # TODO: there's a proper way of getting this info out of peewee fields, do that.
    poobrains.storage.fields.IntegerField: int,
    poobrains.storage.fields.DoubleField: float, 
    poobrains.storage.fields.DateTimeField: datetime.datetime,
    poobrains.storage.fields.CharField: str,
    poobrains.storage.fields.TextField: str,
    poobrains.storage.fields.MarkdownField: str,
}


def fill_valid(instance):

    for attr_name in dir(instance):

        if hasattr(instance.__class__, attr_name):

            cls_attr = getattr(instance.__class__, attr_name)



            if isinstance(cls_attr, poobrains.storage.fields.Field):

                #if instance_attr is None or not cls_attr.primary_key:
                #    import pudb; pudb.set_trace()


                field_class = cls_attr.__class__
                if not cls_attr.null and cls_attr.default is None:
                    if isinstance(cls_attr, poobrains.storage.fields.ForeignKeyField):

                        try:
                            instance_attr = getattr(instance, attr_name)
                        except poobrains.storage.DoesNotExist as e: # only create fk instances if the field hasn't been filled before (i.e. don't mess with existing relations)

                            if cls_attr.rel_model != poobrains.auth.User:

                                ref = cls_attr.rel_model() # create an instance of the related model to reference in this FK column

                                if isinstance(ref, poobrains.auth.Owned):
                                    ref.owner = instance.owner # Means we MUST set owner/group *before* calling fill_valid
                                    ref.group = instance.group

                                fill_valid(ref) # such recursive much wow
                                ref.save(force_insert=True)
                                setattr(instance, attr_name, ref)

                    elif cls_attr.constraints:

                        if isinstance(instance, poobrains.storage.Named) and attr_name == 'name':
                            setattr(instance, attr_name, generators[fieldmap[field_class]]().lower())
                        else:
                            raise AssertionError("Can't guarantee valid fill for class '%s' because of constraints on field '%s'!" % (instance.__class__.__name__, attr_name))

                    elif not fieldmap.has_key(cls_attr.__class__):
                        raise AssertionError("Can't generate fill for %s.%s of type %s" % (instance.__class__.__name__, attr_name, field_class.__name__))
                    else:
                        setattr(instance, attr_name, generators[fieldmap[field_class]]())

                    
# testing setup stuff

#classes_to_test = [poobrains.auth.Page]
classes_to_test = list(poobrains.auth.Owned.class_children()) # what currently works
#classes_to_test = list(poobrains.auth.Administerable.class_children())
#classes_to_test = list(poobrains.auth.Administerable.class_children() - poobrains.auth.Owned.class_children()) # test all non-owned Administerables (all failing administerables should be in here)
ops = list(poobrains.auth.OwnedPermission.op_abbreviations.iteritems()) # crud operations and their abbreviations

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



# tests

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

    passphrase_request = client.get('/cert/') # reply to the next request in the same session contains a flash() with passphrase
    match = re.search(u">The passphrase for this delicious bundle of crypto is &#39;(.+)&#39;<", passphrase_request.data)

    assert match, "Couldn't find passphrase flash!"

    passphrase = match.group(1)

    try:
       OpenSSL.crypto.load_pkcs12(rv.data, passphrase)
    except Exception:
        raise AssertionError("Couldn't load PKCS12 with passphrase '%s'" % passphrase)

# TODO: CRUD tests for ALL non-abstract Storables
@pytest.mark.parametrize('cls', classes_to_test)
def test_crud(client, cls):

    u = poobrains.auth.User.load('root')
    g = u.groups[0]

    instance = cls()
    instance.owner = u
    instance.group = g
    fill_valid(instance)

    assert instance.save(force_insert=True) > 0, "Create failed for class '%s'!" % cls.__name__

    instance = cls.load(instance.handle_string) # reloads instance from database, making sure Read works
    assert instance.owner == u, "Read failed for class '%s'!" % cls.__name__

    # make owner anon to test whether updating works properly
    fill_valid(instance) # put some new values into the instance
    assert instance.save() > 0, "Update failed for class '%s'!" % cls.__name__

    assert instance.delete() > 0, "Delete failed for class '%s'!" % cls.__name__


# TODO: use the Page permission tests as basis for auto-generated permission
# testing of all Protected subclasses. Will need valid value generators for all
# NOT NULL fields first


@pytest.mark.parametrize('op_info', ops, ids=lambda x: x[0])
@pytest.mark.parametrize('cls', classes_to_test)
def test_permission_user_grant(client, cls, op_info):

    op = op_info[0]
    op_abbr = op_info[1]

    u = poobrains.auth.User()
    u.name = 'test-%s-%s-grant' % (cls.__name__.lower(), op)
    u.save(force_insert=True)

    up = poobrains.auth.UserPermission()
    up.user = u
    up.permission = cls.permissions[op].__name__
    up.access = 'grant'
    up.save(force_insert=True)

    u = poobrains.auth.User.load(u.name)

    instance = cls()
    instance.owner = u
    fill_valid(instance)
    instance.save(force_insert=True)

    instance = cls.load(instance.handle_string)

    try:
        instance.permissions[op].check(u)
        instance.delete()
    except poobrains.auth.AccessDenied:
        instance.delete()
        raise AssertionError('User-asigned Permission check for "%s" does not allow access!' % op)


@pytest.mark.parametrize('op_info', ops, ids=lambda x: x[0])
@pytest.mark.parametrize('cls', classes_to_test)
def test_permission_read_user_deny(client, cls, op_info):
    
    op = op_info[0]
    op_abbr = op_info[1]

    u = poobrains.auth.User()
    u.name = 'test-%s-%s-deny' % (cls.__name__.lower(), op)
    u.save(force_insert=True)

    up = poobrains.auth.UserPermission()
    up.user = u
    up.permission = cls.permissions[op].__name__
    up.access = 'deny'
    up.save(force_insert=True)

    u = poobrains.auth.User.load(u.name)

    instance = cls()
    instance.owner = u
    fill_valid(instance)
    instance.save(force_insert=True)

    instance = cls.load(instance.handle_string)

    with pytest.raises(poobrains.auth.AccessDenied):
        instance.permissions[op].check(u)


@pytest.mark.parametrize('op_info', ops, ids=lambda x: x[0])
@pytest.mark.parametrize('cls', classes_to_test)
def test_ownedpermission_user_instance(client, cls, op_info):
    
    op = op_info[0]
    op_abbr = op_info[1]

    u = poobrains.auth.User()
    u.name = 'test-%s-%s-instance' % (cls.__name__.lower(), op)
    u.save(force_insert=True)

    instance = cls()
    instance.owner = u
    fill_valid(instance)
    instance.save(force_insert=True)

    instance = cls.load(instance.handle_string)

    up = poobrains.auth.UserPermission()
    up.user = u
    up.permission = cls.permissions[op].__name__
    up.access = 'instance'
    up.save(force_insert=True)

    u = poobrains.auth.User.load(u.name) # reload user to update own_permissions

    instance.access = ''
    instance.save()
    instance = cls.load(instance.handle_string)

    with pytest.raises(poobrains.auth.AccessDenied, message="!!! FALSE NEGATIVE IN PERMISSION SYSTEM !!! User-assigned OwnedPermission check for '%s' with empty instance access failed!" % op):
        instance.permissions[op].check(u)

    instance.access = op_abbr
    instance.save()
    instance = cls.load(instance.handle_string)

    try:
        instance.permissions[op].check(u)
    except poobrains.auth.AccessDenied:
        raise AssertionError("User-assigned OwnedPermission check for '%s' with instance access '%s' does not allow access!" %(op, op_abbr))


@pytest.mark.parametrize('op_info', ops, ids=lambda x: x[0])
@pytest.mark.parametrize('cls', classes_to_test)
def test_ownedpermission_user_own_instance(client, cls, op_info):
    
    op = op_info[0]
    op_abbr = op_info[1]

    u = poobrains.auth.User()
    u.name = 'test-%s-%s-own-instance' % (cls.__name__.lower(), op)
    u.save(force_insert=True)
    u = poobrains.auth.User.load(u.name) # reload user to update own_permissions
    poobrains.g.user = u # chep login fake because Owned uses g.user as default owner

    instance = cls()
    instance.owner = u
    fill_valid(instance)
    instance.save(force_insert=True)

    instance = cls.load(instance.handle_string)

    up = poobrains.auth.UserPermission()
    up.user = u
    up.permission = cls.permissions[op].__name__
    up.access = 'own_instance'
    up.save(force_insert=True)

    u = poobrains.auth.User.load(u.name) # reload user to update own_permissions

    instance.access = ''
    instance.save()
    instance = cls.load(instance.handle_string)

    with pytest.raises(poobrains.auth.AccessDenied, message="!!! FALSE NEGATIVE IN PERMISSION SYSTEM !!! User-assigned OwnedPermission check for '%s' with empty own_instance access failed!" % op):
        instance.permissions[op].check(u)

    instance.access = op_abbr
    instance.save()
    instance = cls.load(instance.handle_string)

    try:
        instance.permissions[op].check(u)
    except poobrains.auth.AccessDenied:
        raise AssertionError("User-assigned OwnedPermission check for '%s' with own_instance access '%s' does not allow access!" %(op, op_abbr))


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

    # run tests
    pytest.main(['-v', '-s', '--tb=short', os.path.join(poobrains.app.poobrain_path, 'testing.py')])
