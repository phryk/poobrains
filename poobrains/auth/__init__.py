# -*- coding: utf-8 -*-

# external imports
import M2Crypto #import X509, EVP
import pyspkac #import SPKAC
import time
import datetime
import werkzeug
import flask
import peewee

from functools import wraps

# local imports
import poobrains


def admin_listing_actions(cls):

    m = poobrains.rendering.Menu('admin-listing-actions')
    m.append(cls.url('add'), 'add new %s' % (cls.__name__,))

    return m


@poobrains.app.admin.box('menu_main')
def admin_menu():

    menu = poobrains.rendering.Menu('main')
    menu.title = 'Administration'

    for administerable, listings in poobrains.app.admin.listings.iteritems():

        for mode, endpoints in listings.iteritems():

            for endpoint in endpoints: # iterates through endpoints.keys()
                menu.append(flask.url_for('admin.%s' % endpoint), administerable.__name__)

    return menu


@poobrains.app.admin.route('/')
@poobrains.rendering.render()
def admin_index():
    return admin_menu()

def access(*args, **kwargs):

    """
    Decorator; Sets the permission needed to access this page.

    Alternatively, a custom access callback returning True or False might be
    passed.


    Example, using a permission name to determine access rights::

        @app.route('/foo')
        @access('access_foo')
        @view
        def page_foo():
            return value('Here be page content.')


    Example, using a custom access callback to determine access rights::

        def access_anon(user):
            if(user.id == 0):
                return True
            return False

        @app.route('/only/for/anon')
        @access(callback=access_anon)
        @view
        def page_anon():
            return (value('Only anon visitors get access to this.')
      

    ..  warning::
        
        This decorator has to be the below the app.route decorator for the page callback.


    ..  todo::
        
        Check if the custom callback example actually works
    """

    def decorator(func):

        @wraps(func)
        def c(*a, **kw):

            params = {'args': a, 'kwargs': kw}

            kwargs['params'] = params


            if flask.g.user.access(*args, **kwargs):
                return func(*a, **kw)
            else:
                abort(401, "Not authorized for access.")        
        return c

    return decorator


class Permission(poobrains.helpers.ChildAware):
   
    instance = None

    def __init__(self, instance):
        self.instance = instance
        self.check = self.instance_check

    @classmethod
    def check(cls, user):
        return user.access(cls)

#    def instance_check(self):


class AdministerableBase(peewee.BaseModel):

    class Meta:
        abstract = True

    def __new__(cls, *args, **kwargs):

        cls.Create = type('%sCreate' % cls.__name__, (Permission,), {})
        cls.Read   = type('%sRead' % cls.__name__, (Permission,), {})
        cls.Update = type('%sUpdate' % cls.__name__, (Permission,), {})
        cls.Delete = type('%sDelete' % cls.__name__, (Permission,), {})

        return super(AdministerableBase, cls).__new__(cls, *args, **kwargs)


class Administerable(poobrains.storage.Storable):
    
    __metaclass__ = AdministerableBase

    name = poobrains.storage.fields.CharField(index=True, unique=True, constraints=[poobrains.storage.RegexpConstraint('name', '^[a-zA-Z0-9_\-]+$')])
    actions = None

    @property
    def actions(self):

        if not self.id:
            return None

        actions = poobrains.rendering.Menu('%s-%d.actions' % (self.__class__.__name__, self.id))
        try:
            actions.append(self.url('full'), 'View')
            actions.append(self.url('edit'), 'Edit')
            actions.append(self.url('delete'), 'Delete')

        except Exception as e:
            poobrains.app.logger.error('Action menu generation failure.')
            poobrains.app.logger.error(self)

        return actions


    @classmethod
    def load(cls, id_or_name):

        if type(id_or_name) is int or (isinstance(id_or_name, basestring) and id_or_name.isdigit()):
            return super(Administerable, cls).load(id_or_name)

        else:
            return cls.get(cls.name == id_or_name)
    
    
    def __repr__(self):
        return "<%s[%s] %s>" % (self.__class__.__name__, self.id, self.name) if self.id else "<%s, unsaved.>" % self.__class__.__name__


class User(poobrains.storage.Storable):

    name = poobrains.storage.fields.CharField(unique=True)
    groups = None
    permissions = None
    _permissions = None # filled by UserPermission.permission ForeignKeyField

    def prepared(self):

        poobrains.app.logger.debug("User.prepared")
        poobrains.app.logger.debug(self)

        for name, permission in Permission.children_keyed().iteritems():
            poobrains.app.logger.debug(name)
            poobrains.app.logger.debug(permission)

            if permission in self._permissions:
                poobrains.app.logger.debug("permission in granted perms!")


class UserPermission(poobrains.storage.Model):

    user = poobrains.storage.fields.ForeignKeyField(User, related_name='_permissions')
    permission = poobrains.storage.fields.CharField(max_length=50) # deal with it. (⌐■_■)
    access = poobrains.storage.fields.BooleanField()


@poobrains.app.expose('/cert/', force_secure=True)
class ClientCertForm(poobrains.form.Form):
    
    #passphrase = poobrains.form.fields.ObfuscatedText()
    title = "Be safe, certificatisize yourself!"
    token = poobrains.form.fields.ObfuscatedText(label='Token')
    key = poobrains.form.fields.Keygen()
    submit = poobrains.form.Button('submit', label='Generate Certificate')

    def __init__(self, *args, **kwargs):

        super(ClientCertForm, self).__init__(*args, **kwargs)
        flask.session['key_challenge'] = self.key.challenge


    def handle(self, values):

        try:
            token = ClientCertToken.get(ClientCertToken.token == values['token'])

        except Exception as e:
            return poobrains.rendering.RenderString("No such token.")


        try:

            ca_key = M2Crypto.EVP.load_key(poobrains.app.config['CA_KEY'])
            ca_cert = M2Crypto.X509.load_cert(poobrains.app.config['CA_CERT'])

        except Exception as e:

            poobrains.app.logger.error("Client certificate could not be generated. Invalid CA_KEY or CA_CERT.")
            poobrains.app.logger.debug(e)
            return poobrains.rendering.RenderString("Plumbing issue. Invalid CA_KEY or CA_CERT.")


        try:
            spkac = pyspkac.SPKAC(values['key'], flask.session['key_challenge'], CN=token.user.name, Email='fnord@fnord.fnord')
            spkac.push_extension(M2Crypto.X509.new_extension('keyUsage', 'digitalSignature, keyEncipherment, keyAgreement', critical=True))
            spkac.push_extension(M2Crypto.X509.new_extension('extendedKeyUsage', 'clientAuth, emailProtection, nsSGC'))

            spkac.subject.C = ca_cert.get_subject().C

            not_before = int(time.time())
            not_after = not_before + poobrains.app.config['CERT_LIFETIME']

            client_cert = spkac.gen_crt(ca_key, ca_cert, 44, not_before, not_after, hash_algo='sha512')

        except Exception as e:

            if poobrains.app.debug:
                raise

            return poobrains.rendering.RenderString("Client certificate creation failed.")

        try:
            cert_info = ClientCert()
            cert_info.name = token.name
            cert_info.user = token.user
            #cert_info.pubkey = client_cert.get_pubkey().as_pem(cipher=None) # We don't even need the pubkey. subject distinguished name should™ work just as well.
            cert_info.subject_name = unicode(client_cert.get_subject())
            cert_info.save()

        except Exception as e:

            if poobrains.app.debug:
                raise

            return poobrains.rendering.RenderString("Failed to write info into database. Disregard this certificate.")

        r = werkzeug.wrappers.Response(client_cert.as_pem())
        r.mimetype = 'application/x-x509-user-cert'
        return r

class ClientCertToken(poobrains.storage.Storable):

    validity = None
    user = poobrains.storage.fields.ForeignKeyField(User)
    created = poobrains.storage.fields.DateTimeField(default=datetime.datetime.now)
    token = poobrains.storage.fields.CharField(unique=True)
    # passphrase = poobrains.storage.fields.CharField(null=True) # TODO: Find out whether we can pkcs#12 encrypt client certs with a passphrase and make browsers still eat it.
    redeemed = poobrains.storage.fields.BooleanField()


    def __init__(self, *args, **kw):

        self.validity = poobrains.app.config['TOKEN_VALIDITY']
        super(ClientCertToken, self).__init__(*args, **kw)


class ClientCert(poobrains.storage.Storable):

    user = poobrains.storage.fields.ForeignKeyField(User)
    subject_name = poobrains.storage.fields.CharField()
