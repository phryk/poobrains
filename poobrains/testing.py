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

def generate_bool():

    return bool(random.randint(0, 1))


def generate_int():

    return 4 # guaranteed to be random by fair dice roll


def generate_float():

    return 5.55


generators = {
    bool: generate_bool,
    int: generate_int,
    float: generate_float,
    str: poobrains.helpers.random_string_light,
    datetime.datetime: datetime.datetime.now
}

fieldmap = { # TODO: there's a proper way of getting this info out of peewee fields, do that.
    poobrains.storage.fields.BooleanField: bool,
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

                field_class = cls_attr.__class__
                if not cls_attr.null and cls_attr.default is None:
                    if isinstance(cls_attr, poobrains.storage.fields.ForeignKeyField):

                        try:
                            instance_attr = getattr(instance, attr_name)

                        except poobrains.storage.DoesNotExist as e: # only create fk instances if the field hasn't been filled before (i.e. don't mess with existing relations)

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

                    elif not cls_attr.__class__ in fieldmap:
                        raise AssertionError("Can't generate fill for %s.%s of type %s" % (instance.__class__.__name__, attr_name, field_class.__name__))
                    else:
                        setattr(instance, attr_name, generators[fieldmap[field_class]]())

                    
# testing setup stuff

expected_failures = set([ # set of Storables we know will fail automatic testing while being valid. mostly caused by constraints and minimal table structure (linker tables for example). these types will need their own tests.
    poobrains.auth.UserGroup, # all columns member of a CompositeKey, meaning updating isn't really a thing
    poobrains.auth.UserPermission, # similar issue as UserGroup, but has one more field which is basically a runtime enum, i.e. what's valid is determined by poobrains and not the db
    poobrains.auth.GroupPermission, # ditto
    poobrains.auth.ClientCertToken, # regexp constraint on cert_name
])

storables_to_test = list(poobrains.storage.Storable.class_children() - expected_failures)
administerables_to_test = list(poobrains.auth.Administerable.class_children() - expected_failures)
owneds_to_test = list(poobrains.auth.Owned.class_children() - expected_failures) # what currently works

permission_holders = ['user', 'group']

ops = list(poobrains.auth.OwnedPermission.op_abbreviations.items()) # crud operations and their abbreviations

@pytest.fixture
def client():

    poobrains.app.wsgi_app = FakeHTTPSMiddleware(poobrains.app.wsgi_app)
    poobrains.app.config['SECRET_KEY'] = 'fnord'
    poobrains.app.config['TESTING'] = True
    poobrains.app.debug = True
    client = poobrains.app.test_client()

    if not 'FLASK_APP' in os.environ:
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
    print(rv.output)

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

    passphrase_response = client.get('/cert/') # reply to the next request in the same session contains a flash() with passphrase
    match = re.search(u">The passphrase for this delicious bundle of crypto is &#39;(.+)&#39;<", passphrase_response.data.decode('ascii'))

    assert match, "Couldn't find passphrase flash!"

    passphrase = match.group(1)

    try:
       OpenSSL.crypto.load_pkcs12(rv.data, passphrase)
    except Exception:
        raise AssertionError("Couldn't load PKCS12 with passphrase '%s'" % passphrase)

# TODO: CRUD tests for ALL non-abstract Storables
@pytest.mark.parametrize('cls', storables_to_test)
def test_crud(client, cls):

    u = poobrains.auth.User.load('root')
    g = u.groups[0]

    instance = cls()

    if isinstance(instance, poobrains.auth.Owned):
        instance.owner = u
        instance.group = g

    fill_valid(instance)

    assert instance.save(force_insert=True) > 0, "Create failed for class '%s'!" % cls.__name__

    try:
        instance = cls.load(instance.handle_string) # reloads instance from database, making sure Read works
    except cls.DoesNotExist:
        raise AssertionError("Read failed for class '%s'!" % cls.__name__)

    # make owner anon to test whether updating works properly
    fill_valid(instance) # put some new values into the instance
    
    assert instance.save() > 0, "Update failed for class '%s'!" % cls.__name__

    assert instance.delete_instance() > 0, "Delete failed for class '%s'!" % cls.__name__


# TODO: use the Page permission tests as basis for auto-generated permission
# testing of all Protected subclasses. Will need valid value generators for all
# NOT NULL fields first


@pytest.mark.parametrize('op_info', ops, ids=lambda x: x[0])
@pytest.mark.parametrize('permission_holder', permission_holders)
@pytest.mark.parametrize('cls', administerables_to_test)
def test_permission_grant(client, cls, permission_holder, op_info):

    op = op_info[0]
    op_abbr = op_info[1]

    if not op in cls.permissions:
        pytest.skip() # this op has been explicitly disabled and isn't exposed (for which there should also be a test)

    u = poobrains.auth.User()
    u.name = 'test-%s-%s-%s-grant' % (cls.__name__.lower(), permission_holder, op)
    u.save(force_insert=True)

    instance = cls()
    if isinstance(instance, poobrains.auth.Owned):
        instance.owner = u

    if permission_holder == 'user':

        up = poobrains.auth.UserPermission()
        up.user = u
        up.permission = cls.permissions[op].__name__
        up.access = 'grant'
        up.save(force_insert=True)

    else: # group
        
        g = poobrains.auth.Group()
        g.name = '%s-%s-group-grant' % (cls.__name__.lower(), op)
        g.save(force_insert=True)

        ug = poobrains.auth.UserGroup()
        ug.user = u
        ug.group = g
        ug.save(force_insert=True)

        gp = poobrains.auth.GroupPermission()
        gp.group = g
        gp.permission = cls.permissions[op].__name__
        gp.access = 'grant'
        gp.save(force_insert=True)

        if isinstance(instance, poobrains.auth.Owned):
            instance.group = g

    u = poobrains.auth.User.load(u.name)

    fill_valid(instance)
    instance.save(force_insert=True)

    instance = cls.load(instance.handle_string)

    try:
        instance.permissions[op].check(u)
    except poobrains.auth.AccessDenied:
        raise AssertionError("%s-assigned Permission check on %s for '%s' does not allow access!" % (permission_holder, cls.__name__, op))


@pytest.mark.parametrize('op_info', ops, ids=lambda x: x[0])
@pytest.mark.parametrize('permission_holder', permission_holders)
@pytest.mark.parametrize('cls', administerables_to_test)
def test_permission_deny(client, cls, permission_holder, op_info):
    
    op = op_info[0]
    op_abbr = op_info[1]

    if not op in cls.permissions:
        pytest.skip() # this op has been explicitly disabled and isn't exposed (for which there should also be a test)

    u = poobrains.auth.User()
    u.name = 'test-%s-%s-%s-deny' % (cls.__name__.lower(), permission_holder, op)
    u.save(force_insert=True)
    
    instance = cls()
    if isinstance(instance, poobrains.auth.Owned):
        instance.owner = u
    
    if permission_holder == 'user':

        up = poobrains.auth.UserPermission()
        up.user = u
        up.permission = cls.permissions[op].__name__
        up.access = 'deny'
        up.save(force_insert=True)

    else: # group
        
        g = poobrains.auth.Group()
        g.name = '%s-%s-group-deny' % (cls.__name__.lower(), op)
        g.save(force_insert=True)

        ug = poobrains.auth.UserGroup()
        ug.user = u
        ug.group = g
        ug.save(force_insert=True)

        gp = poobrains.auth.GroupPermission()
        gp.group = g
        gp.permission = cls.permissions[op].__name__
        gp.access = 'deny'
        gp.save(force_insert=True)

        if isinstance(instance, poobrains.auth.Owned):
            instance.group = g

    u = poobrains.auth.User.load(u.name)

    fill_valid(instance)
    instance.save(force_insert=True)

    instance = cls.load(instance.handle_string)

    with pytest.raises(poobrains.auth.AccessDenied):
        instance.permissions[op].check(u)


@pytest.mark.parametrize('op_info', ops, ids=lambda x: x[0])
@pytest.mark.parametrize('permission_holder', permission_holders)
@pytest.mark.parametrize('cls', owneds_to_test)
def test_ownedpermission_instance(client, cls, permission_holder, op_info):
    
    op = op_info[0]
    op_abbr = op_info[1]

    if not op in cls.permissions:
        pytest.skip() # this op has been explicitly disabled and isn't exposed (for which there should also be a test)

    u = poobrains.auth.User()
    u.name = 'test-%s-%s-%s-instance' % (cls.__name__.lower(), permission_holder, op)
    u.save(force_insert=True)

    instance = cls()
    instance.owner = u
    fill_valid(instance)
    instance.save(force_insert=True)

    instance = cls.load(instance.handle_string)
    
    if permission_holder == 'user':

        up = poobrains.auth.UserPermission()
        up.user = u
        up.permission = cls.permissions[op].__name__
        up.access = 'instance'
        up.save(force_insert=True)
    
    else: # group
        
        g = poobrains.auth.Group()
        g.name = '%s-%s-group-instance' % (cls.__name__.lower(), op)
        g.save(force_insert=True)

        ug = poobrains.auth.UserGroup()
        ug.user = u
        ug.group = g
        ug.save(force_insert=True)

        gp = poobrains.auth.GroupPermission()
        gp.group = g
        gp.permission = cls.permissions[op].__name__
        gp.access = 'instance'
        gp.save(force_insert=True)

        instance.group = g

    u = poobrains.auth.User.load(u.name) # reload user to update own_permissions

    instance.access = ''
    instance.save()
    instance = cls.load(instance.handle_string)

    with pytest.raises(poobrains.auth.AccessDenied, message="!!! FALSE NEGATIVE IN PERMISSION SYSTEM !!! User-assigned OwnedPermission check on %s for '%s' with empty instance access failed!" % (cls.__name__, op)):
        instance.permissions[op].check(u)

    instance.access = op_abbr
    instance.save()
    instance = cls.load(instance.handle_string)

    try:
        instance.permissions[op].check(u)
    except poobrains.auth.AccessDenied:
        raise AssertionError("%s-assigned OwnedPermission check on %s for '%s' with instance access '%s' does not allow access!" % (permission_holder, cls.__name__, op, op_abbr))


@pytest.mark.parametrize('op_info', ops, ids=lambda x: x[0])
@pytest.mark.parametrize('permission_holder', permission_holders)
@pytest.mark.parametrize('cls', owneds_to_test)
def test_ownedpermission_own_instance(client, cls, permission_holder, op_info):
    
    op = op_info[0]
    op_abbr = op_info[1]

    if not op in cls.permissions:
        pytest.skip() # this op has been explicitly disabled and isn't exposed (for which there should also be a test)

    u = poobrains.auth.User()
    u.name = 'test-%s-%s-%s-own-instance' % (cls.__name__.lower(), permission_holder, op)
    u.save(force_insert=True)
    u = poobrains.auth.User.load(u.name) # reload user to update own_permissions
    poobrains.g.user = u # chep login fake because Owned uses g.user as default owner

    instance = cls()
    instance.owner = u
    fill_valid(instance)
    instance.save(force_insert=True)

    instance = cls.load(instance.handle_string)
    
    if permission_holder == 'user':

        up = poobrains.auth.UserPermission()
        up.user = u
        up.permission = cls.permissions[op].__name__
        up.access = 'own_instance'
        up.save(force_insert=True)
    
    else: # group
        
        g = poobrains.auth.Group()
        g.name = '%s-%s-group-own-instance' % (cls.__name__.lower(), op)
        g.save(force_insert=True)

        ug = poobrains.auth.UserGroup()
        ug.user = u
        ug.group = g
        ug.save(force_insert=True)

        gp = poobrains.auth.GroupPermission()
        gp.group = g
        gp.permission = cls.permissions[op].__name__
        gp.access = 'own_instance'
        gp.save(force_insert=True)

        instance.group = g

    u = poobrains.auth.User.load(u.name) # reload user to update own_permissions

    instance.access = ''
    instance.save()
    instance = cls.load(instance.handle_string)

    with pytest.raises(poobrains.auth.AccessDenied, message="!!! FALSE NEGATIVE IN PERMISSION SYSTEM !!! User-assigned OwnedPermission check on %s for '%s' with empty own_instance access failed!" % (cls.__name__, op)):
        instance.permissions[op].check(u)

    instance.access = op_abbr
    instance.save()
    instance = cls.load(instance.handle_string)

    try:
        instance.permissions[op].check(u)
    except poobrains.auth.AccessDenied:
        raise AssertionError("%s-assigned OwnedPermission check on %s for '%s' with own_instance access '%s' does not allow access!" % (permission_holder, cls.__name__, op, op_abbr))


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
