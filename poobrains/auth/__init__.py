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
@poobrains.helpers.render()
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


    def handle(self):

        try:
            token = ClientCertToken.get(ClientCertToken.token == self.fields['token'].value)

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
            spkac = pyspkac.SPKAC(self.fields['key'].value, flask.session['key_challenge'], CN=token.user.name, Email='fnord@fnord.fnord')
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


class RelatedForm(poobrains.form.Form):
   
    instance = None
    related_model = None
    related_field = None

    def __new__(cls, related_model, related_field, instance, name=None, title=None, method=None, action=None):

        f = super(RelatedForm, cls).__new__(cls, name=name, title=title, method=method, action=action)

        for related_instance in getattr(instance, related_field.related_name):
            #key = '%s-%d-edit' % (related_model.__name__, related_instance.id)
            key = related_instance.id_string
            #f.fields[key] = poobrains.form.EditFieldset(related_instance)
            #f.fields[key] = related_instance.fieldset_edit()
            setattr(f, key, related_instance.fieldset_edit())

            if f.fields[key].fields.has_key(related_field.name):
                #f.fields[key].fields[related_field.name] = poobrains.form.fields.Value(value=instance.id) # TODO: Won't work with `CompositeKeyField`s
                setattr(f.fields[key], related_field.name, poobrains.form.fields.Value(value=instance.id)) # TODO: Won't work with `CompositeKeyField`s


        related_instance = related_model()
        setattr(related_instance, related_field.name, instance) 
        #key = '%s-add' % related_model.__name__
        key = related_instance.id_string

        #f.fields[key] = poobrains.form.AddFieldset(related_instance)
        setattr(f, key, related_instance.fieldset_add())

        if f.fields[key].fields.has_key(related_field.name):
            #f.fields[key].fields[related_field.name] = poobrains.form.fields.Value(value=instance.id) # TODO: Won't work with `CompositeKeyField`s
            setattr(f.fields[key], related_field.name, poobrains.form.fields.Value(value=instance.id)) # TODO: Won't work with `CompositeKeyField`s
        else:
            poobrains.app.logger.debug("We need that 'if' after all! Do we maybe have a CompositeKeyField primary key in %s?" % self.related_model.__name__)
            
        f.controls['reset'] = poobrains.form.Button('reset', label='Reset')
        f.controls['submit'] = poobrains.form.Button('submit', name='submit', value='submit', label='Save')

        return f

    
    def __init__(self, related_model, related_field, instance, id_or_name=None, prefix=None, name=None, title=None, method=None, action=None):
        super(RelatedForm, self).__init__(prefix=None, name=None, title=None, method=None, action=None)

        self.instance = instance
        self.related_model = related_model
        self.related_field = related_field

    
    def view(self, mode=None):

        """
        view function to be called in a flask request context
        """
        if flask.request.method == self.method:

            values = flask.request.form[self.name]

            for field in self:

                if not field.empty():
                    try:
                        field.validate(values[field.name])

                        try:

                            field.bind(values[field.name])

                            if isinstance(field, poobrains.form.Fieldset) and not field.errors:
                                field.handle()
                                flask.flash("Handled %s.%s" % (field.prefix, field.name))
                            else:
                                flask.flash("Not handled:")
                                flask.flash(field.empty())


                        except poobrains.form.errors.BindingError as e:
                            flask.flash(e.message)

                    except (poobrains.form.errors.ValidationError, poobrains.form.errors.CompoundError) as e:
                        flask.flash(e.message)

                try:

                    if hasattr(field, 'empty_value'):
                        default = field.empty_value
                    else:
                        default = None
                    field.bind(values[field.name]) # bind to show erroneous values to user
                except poobrains.form.errors.BindingError as e:
                    flask.flash(e.message)


        return self
   

    def handle(self):

        for field in self.fields.itervalues():
            if isinstance(field, poobrains.form.Fieldset):
                field.handle()
        return flask.redirect(flask.request.url)


class UserPermissionAddFieldset(poobrains.form.AddFieldset):

    def empty(self):
        rv = self.fields['permission'].empty()
        return rv

class UserPermissionEditFieldset(UserPermissionAddFieldset):

    def __new__(cls, model_or_instance, mode='edit', prefix=None, name=None, title=None, method=None, action=None):
        return super(UserPermissionEditFieldset, cls).__new__(cls, model_or_instance, mode=mode, prefix=prefix, name=name, title=title, method=method, action=action)
   

    def __init__(self, model_or_instance, mode='edit', prefix=None, name=None, title=None, method=None, action=None):
        super(UserPermissionEditFieldset, self).__init__(model_or_instance, mode=mode, prefix=prefix, name=name, title=title, method=method, action=action)
 

class UserPermissionRelatedForm(RelatedForm):

    def __new__(cls, related_model, related_field, instance, name=None, title=None, method=None, action=None):

        f = super(UserPermissionRelatedForm, cls).__new__(cls, related_model, related_field, instance, name=name, title=title, method=method, action=action)

        f.fields.clear() # probably not the most efficient way to have proper form setup without the fields

        for name, perm in Permission.children_keyed().iteritems(): # TODO: sorting doesn't help, problem with/CustomOrderedDict?

            try:
                perm_info = UserPermission.get(UserPermission.user == instance and UserPermission.permission == perm.__name__)
                perm_mode = 'edit'

                #f.fields[perm.__name__] = poobrains.form.EditFieldset(perm_info, mode=perm_mode, name=perm.__name__)
                #f.fields[perm.__name__] = perm_info.fieldset_edit(mode=perm_mode)
                setattr(f, perm.__name__, perm_info.fieldset_edit(mode=perm_mode))

            except:
                perm_info = UserPermission()
                perm_info.user = instance
                perm_info.permission = perm.__name__
                perm_info.access = None
                perm_mode = 'add'

                #f.fields[perm.__name__] = poobrains.form.AddFieldset(perm_info, mode=perm_mode, name=perm.__name__)
                #f.fields[perm.__name__] = perm_info.fieldset_add(mode=perm_mode)
                setattr(f, perm.__name__, perm_info.fieldset_add(mode=perm_mode))

        return f


#    def handle(self):
#        self.instance.permissions.clear()
#        for perm_fieldset in self.fields.itervalues():
#            if perm_fieldset.fields['access'].value:
#                self.instance.permissions[perm_fieldset.fields['permission'].value] = perm_fieldset.fields['access'].value

        #response = super(UserPermissionRelatedForm, self).handle()

#        for name, perm in Permission.children_keyed().items()
#        return flask.redirect(flask.request.url)


class Permission(poobrains.helpers.ChildAware):
   
    instance = None

    class Meta:
        abstract = True

    def __init__(self, instance):
        self.instance = instance
        self.check = self.instance_check

    @classmethod
    def check(cls, user):
        return user.access(cls)

    def instance_check(self, user):
        pass


class BaseAdministerable(poobrains.storage.BaseModel):

    """
    Metaclass for `Administerable`s.
    """

    def __new__(cls, name, bases, attrs):

        cls = super(BaseAdministerable, cls).__new__(cls, name, bases, attrs)

        perm_attrs = {}
        if hasattr(cls, '_meta') and hasattr(cls._meta, 'abstract') and cls._meta.abstract:

            class Meta:
                abstract = True

            perm_attrs['Meta'] = Meta # Makes Permissions for abstract Administerables abstract, too

        cls.Create = type('%sCreate' % name, (Permission,), perm_attrs)
        cls.Read   = type('%sRead' % name, (Permission,), perm_attrs)
        cls.Update = type('%sUpdate' % name, (Permission,), perm_attrs)
        cls.Delete = type('%sDelete' % name, (Permission,), perm_attrs)

        return cls


class Administerable(poobrains.storage.Storable, poobrains.helpers.ChildAware):
    
    __metaclass__ = BaseAdministerable

    form_modes = ['add', 'edit', 'delete']
    form_add = poobrains.form.AddForm
    form_edit = poobrains.form.EditForm
    form_delete = poobrains.form.DeleteForm

    fieldset_add = poobrains.form.AddFieldset
    fieldset_edit = poobrains.form.EditFieldset
    #fieldset_delete = poobrains.form.DeleteFieldset doesn't yet exist, and isn't used.

    related_form = RelatedForm # TODO: make naming consistent

    class Meta:
        abstract = True
    
    actions = None

    @property
    def actions(self):

        if not self.id:
            return None

        actions = poobrains.rendering.Menu('%s.actions' % self.id_string)
        try:
            actions.append(self.url('full'), 'View')

        except LookupError:
            poobrains.app.logger.debug("Couldn't create view link for %s" % self.id_string)

        try:
            actions.append(self.url('edit'), 'Edit')

        except LookupError:
            poobrains.app.logger.debug("Couldn't create edit link for %s" % self.id_string)

        try:
            actions.append(self.url('delete'), 'Delete')

        except LookupError:
            poobrains.app.logger.debug("Couldn't create delete link for %s" % self.id_string)

        return actions


    def form(self, mode=None):

        if not mode in self.form_modes:
            raise ValueError("%s is not a valid form mode for %s." % (mode, self.__class__.__name__))

        n = 'form_%s' % mode
        if not hasattr(self, n):
            raise NotImplementedError("Form class %s.%s missing." % (self.__class__.__name__, n))

        form_class = getattr(self, n)
        return form_class(mode=mode)#, name=None, title=None, method=None, action=None)
    

    def view(self, mode=None):

        """
        view function to be called in a flask request context
        """

        if mode in self.form_modes:

            f = self.form(mode)
            return f.view(mode)

        return self


    def __repr__(self):
        return "<%s[%s] %s>" % (self.__class__.__name__, self.id, self.name) if self.id else "<%s, unsaved.>" % self.__class__.__name__


class NamedAdministerable(Administerable, poobrains.storage.Named):

    class Meta:
        abstract = True
    
    @classmethod
    def load(cls, id_or_name):
        if type(id_or_name) is int or (isinstance(id_or_name, basestring) and id_or_name.isdigit()):
            return super(Administerable, cls).load(id_or_name)

        else:
            return cls.get(cls.name == id_or_name)


class User(NamedAdministerable):

    #name = poobrains.storage.fields.CharField(unique=True)
    groups = None
    permissions = None
    _permissions = None # filled by UserPermission.permission ForeignKeyField

    #form = UserForm

    def __init__(self, *args, **kwargs):

        super(User, self).__init__(*args, **kwargs)
        self.permissions = {}


    def prepared(self):

        for up in self._permissions:
            self.permissions[up.permission] = up.access

    
    def save(self, *args, **kwargs):

        super(User, self).save(*args, **kwargs)

        rv = UserPermission.delete().where(UserPermission.user == self)

        for perm_name, access in self.permissions.iteritems():
            up = UserPermission()
            up.user = self
            up.permission = perm_name
            up.access = access
            up.save()

        return rv


class UserPermission(Administerable):

    fieldset_add = UserPermissionAddFieldset
    fieldset_edit = UserPermissionEditFieldset

    class Meta:
        primary_key = peewee.CompositeKey('user', 'permission')
        order_by = ('user', 'permission')

    user = poobrains.storage.fields.ForeignKeyField(User, related_name='_permissions')
    permission = poobrains.storage.fields.CharField(max_length=50) # deal with it. (⌐■_■)
    access = poobrains.storage.fields.CharField(max_length=4, null=False, choices=[(None, 'Ignore'), ('all', 'For all instances'), ('own', 'For own instances'), ('deny', 'Explicitly deny')])
    access.form_class = poobrains.form.fields.TextChoice

    related_form = UserPermissionRelatedForm


    @classmethod
    def load(cls, id_perm_string):

        (user_id, permission) = id_perm_string.split(',')
        user = User.load(user_id)
        return cls.get(cls.user == user, cls.permission == permission)


class ClientCertToken(Administerable):

    validity = None
    user = poobrains.storage.fields.ForeignKeyField(User)
    created = poobrains.storage.fields.DateTimeField(default=datetime.datetime.now, null=False)
    token = poobrains.storage.fields.CharField(unique=True)
    # passphrase = poobrains.storage.fields.CharField(null=True) # TODO: Find out whether we can pkcs#12 encrypt client certs with a passphrase and make browsers still eat it.
    redeemed = poobrains.storage.fields.BooleanField()


    def __init__(self, *args, **kw):

        self.validity = poobrains.app.config['TOKEN_VALIDITY']
        super(ClientCertToken, self).__init__(*args, **kw)


class ClientCert(Administerable):

    form_blacklist = ['id', 'user', 'subject_name']

    user = poobrains.storage.fields.ForeignKeyField(User)
    subject_name = poobrains.storage.fields.CharField()


