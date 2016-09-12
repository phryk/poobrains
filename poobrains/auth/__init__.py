# -*- coding: utf-8 -*-

# external imports
import functools
import collections
import M2Crypto #import X509, EVP
import pyspkac #import SPKAC
import time
import datetime
import werkzeug
import flask
import peewee


# local imports
import poobrains


class PermissionDenied(werkzeug.exceptions.HTTPException):
    code = 403


class Permission(poobrains.helpers.ChildAware):
   
    instance = None
    mode = None
    label = None
    choices = [('grant', 'Grant'), ('deny', 'Explicitly deny')]

    class Meta:
        abstract = True

    def __init__(self, instance):
        self.instance = instance
        self.check = self.instance_check

    @classmethod
    def check(cls, user):

        # check user-assigned permission state
        if user.own_permissions.has_key(cls.__name__):
            access = user.own_permissions[cls.__name__]

            if access == 'deny':
                raise PermissionDenied("YOU SHALL NOT PASS!")

            elif access == 'grant':
                return True

        # check if user is member of any groups with 'deny' for this permission
        group_deny = GroupPermission.select().join(Group).join(UserGroup).join(User).where(UserGroup.user == user, GroupPermission.permission == cls.__name__, GroupPermission.access == 'deny').count()

        if group_deny:
            raise PermissionDenied("YOU SHALL NOT PASS!")

        group_grant = GroupPermission.select().join(Group).join(UserGroup).join(User).where(UserGroup.user == user, GroupPermission.permission == cls.__name__, GroupPermission.access == 'grant').count()

        if group_grant:
            return True

        raise PermissionDenied("YOU SHALL NOT PASS!")



    def instance_check(self, user):
        return self.__class__.check(user)


class PermissionInjection(poobrains.helpers.MetaCompatibility):

    def __new__(cls, name, bases, attrs):
        
        cls = super(PermissionInjection, cls).__new__(cls, name, bases, attrs)
        #cls._meta.permissions = collections.OrderedDict()
        cls.permissions = collections.OrderedDict()

        for mode in cls._meta.modes:
            perm_name = "%s_%s" % (cls.__name__, mode)
            perm_label = "%s %s" % (mode.capitalize(), cls.__name__)
            #cls._meta.permissions[mode] = type(perm_name, (cls._meta.permission_class,), {})
            perm_attrs = dict()

            if hasattr(cls._meta, 'abstract') and cls._meta.abstract:

                # Make permissions belonging to abstract Renderables abstract as well
                #FIXME: I have no clue why both _meta and Meta are needed, grok it, simplify if sensible

                meta = poobrains.helpers.FakeMetaOptions()
                meta.abstract = True
                perm_attrs['_meta'] = meta
                perm_attrs['mode'] = mode

                class Meta:
                    abstract = True

                perm_attrs['Meta'] = Meta
            
            cls.permissions[mode] = type(perm_name, (cls._meta.permission_class,), perm_attrs)

        return cls


#def get_permission(permission_name):
#
#    for perm in Permission.children():
#        if permission_name == perm.__name__:
#            return perm
#
#    raise LookupError("Unknown permission: %s" % str(permission_name))


class FormPermissionField(poobrains.form.fields.Choice):

    def __init__(self, *args, **kwargs):

        super(FormPermissionField, self).__init__(*args, **kwargs)

        self.choices = []
        for perm_name, perm in Permission.children_keyed().iteritems():
            self.choices.append(([('%s.%s' % (perm_name, value), label) for (value, label) in perm.choices], perm_name))


    def validate(self):

        permission, mode = self.value

        if not permission in Permission.children_keyed().keys():
            raise poobrains.form.errors.ValidationError('Unknown permission: %s' % permission)

        perm_class = Permission.children_keyed()[permission]
        if not access in perm_class.choices:
            raise poobrains.form.errors.ValidationError("Unknown access mode '%s' for permission '%s'." % (access, permission))

    
    def coercer(self, value):

        cleaned_string = poobrains.form.coercers.coerce_string(value)

        try:
            rv = cleaned_string.split('.')
        except Exception as e:
            raise poobrains.form.errors.ValidationError('Could not split value to permission and access: %s' % cleaned_string)

        return rv
    

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
@poobrains.helpers.themed
def admin_index():
    return admin_menu()




#def access(*args, **kwargs):
#
#    """
#    Decorator; Sets the permission needed to access this page.
#
#    Alternatively, a custom access callback returning True or False might be
#    passed.
#
#
#    Example, using a permission name to determine access rights::
#
#        @app.route('/foo')
#        @access('access_foo')
#        @view
#        def page_foo():
#            return value('Here be page content.')
#
#
#    Example, using a custom access callback to determine access rights::
#
#        def access_anon(user):
#            if(user.id == 0):
#                return True
#            return False
#
#        @app.route('/only/for/anon')
#        @access(callback=access_anon)
#        @view
#        def page_anon():
#            return (value('Only anon visitors get access to this.')
#      
#
#    ..  warning::
#        
#        This decorator has to be the below the app.route decorator for the page callback.
#
#
#    ..  todo::
#        
#        Check if the custom callback example actually works
#    """
#
#    def decorator(func):
#
#        @wraps(func)
#        def c(*a, **kw):
#
#            params = {'args': a, 'kwargs': kw}
#
#            kwargs['params'] = params
#
#
#            if flask.g.user.access(*args, **kwargs):
#                return func(*a, **kw)
#            else:
#                abort(401, "Not authorized for access.")        
#        return c
#
#    return decorator


def access(permission):

    def decorator(func):

        @functools.wraps(func)
        def substitute(*args, **kwargs):

            print "ACCESS SUB", args, kwargs 

            return func(*args, **kwargs)

        return substitute

    return decorator


def protected(func):

    @functools.wraps(func)
    #def substitute(cls_or_instance, *args, **kwargs):
    def substitute(cls_or_instance, mode, *args, **kwargs):

        poobrains.app.logger.debug('protected call cls_or_instance: %s, %s', cls_or_instance, dir(cls_or_instance))

        user = flask.g.user # FIXME: How do I get rid of the smell?

        if not ((isinstance(cls_or_instance, type) and issubclass(cls_or_instance, Protected)) or isinstance(cls_or_instance, Protected)):
            raise ValueError("@protected used with non-protected class '%s'." % cls_or_instance.__class__.__name__)

        if not cls_or_instance.permissions.has_key(mode):
            raise NotImplementedError("Did not find permission for mode '%s' in cls_or_instance of class '%s'." % (mode, cls_or_instance.__class__.__name__))
        

        cls_or_instance.permissions[mode].check(user)

        #return func(cls_or_instance, *args, **kwargs)
        return func(cls_or_instance, mode, *args, **kwargs)

    return substitute


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

            serial = int(time.time())

            client_cert = spkac.gen_crt(ca_key, ca_cert, serial, not_before, not_after, hash_algo='sha512')

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

        token.redeemed = True
        token.save()

        r = werkzeug.wrappers.Response(client_cert.as_pem())
        r.mimetype = 'application/x-x509-user-cert'
        return r

    @poobrains.helpers.is_secure
    def view(self, *args, **kwargs):
        return super(ClientCertForm, self).view(*args, **kwargs)


class OwnedPermission(Permission):
    choices = [('all', 'For all instances'), ('own', 'For own instances'), ('deny', 'Explicitly deny')]
    
    class Meta:
        abstract = True

    @classmethod
    def check(cls, user):

        if user.own_permissions.has_key(cls.__name__):
            access = user.own_permissions[cls.__name__]

            if access == 'deny':
                raise PermissionDenied("YOU SHALL NOT PASS!")

            elif access == 'own':
                return True

            elif access == 'all':
                return True

            else:
                poobrains.app.logger.warning("Unknown access mode '%s' for User %d with Permission %s" % (access, user.id, cls.__name__))
                raise PermissionDenied("YOU SHALL NOT PASS!")


    def instance_check(self, user):
        
        if user.own_permissions.has_key(self.__class__.__name__):

            access = user.own_permissions[self.__class__.__name__]

            if access == 'deny':
                raise PermissionDenied("YOU SHALL NOT PASS!")

            elif access == 'own':
                if self.instance.owner == user and self.mode in self.instance.owner_mode.split(':'):
                    return True
                else:
                    raise PermissionDenied("YOU SHALL NOT PASS!")

            elif access == 'all':
                return True

            else:
                raise PermissionDenied("YOU SHALL NOT PASS!")


        group_deny = GroupPermission.select().join(Group).join(UserGroup).join(User).where(UserGroup.user == user, GroupPermission.permission == self.__class__.__name__, GroupPermission.access == 'deny').count()

        if group_deny:
            raise PermissionDenied("YOU SHALL NOT PASS!")

        group_own = GroupPermission.select().join(Group).join(UserGroup).join(User).where(UserGroup.user == user, GroupPermission.permission == self.__class__.__name__, GroupPermission.access == 'own').count()

        if group_own:
            if self.mode in self.instance.group_mode.split(':'):
                return True
            else:
                raise PermissionDenied("YOU SHALL NOT PASS!")


        group_all = GroupPermission.select().join(Group).join(UserGroup).join(User).where(UserGroup.user == user, GroupPermission.permission == self.__class__.__name__, GroupPermission.access == 'all').count()

        if group_all:
            return True

        raise PermissionDenied("YOU SHALL NOT PASS!") # Implicit denial


class RelatedForm(poobrains.form.Form):
   
    instance = None
    related_model = None
    related_field = None

    def __new__(cls, related_model, related_field, instance, name=None, title=None, method=None, action=None):

        f = super(RelatedForm, cls).__new__(cls, name=name, title=title, method=method, action=action)

        for related_instance in getattr(instance, related_field.related_name):

            # Fieldset to edit an existing related instance of this instance

            #key = '%s-%d-edit' % (related_model.__name__, related_instance.id)
            key = related_instance.handle_string
            #f.fields[key] = poobrains.form.EditFieldset(related_instance)
            #f.fields[key] = related_instance.fieldset_edit()
            setattr(f, key, related_instance.fieldset_edit())

            if f.fields[key].fields.has_key(related_field.name):
                #f.fields[key].fields[related_field.name] = poobrains.form.fields.Value(value=instance.id) # FIXME: Won't work with `CompositeKeyField`s
                #setattr(f.fields[key], related_field.name, poobrains.form.fields.Value(value=instance.id)) # FIXME: Won't work with `CompositeKeyField`s
                setattr(f.fields[key], related_field.name, poobrains.form.fields.Value(value=instance._get_pk_value()))


        # Fieldset to add a new related instance to this instance
        related_instance = related_model()
        setattr(related_instance, related_field.name, instance) 
        #key = '%s-add' % related_model.__name__
        key = related_instance.handle_string

        #f.fields[key] = poobrains.form.AddFieldset(related_instance)
        setattr(f, key, related_instance.fieldset_add())

        if f.fields[key].fields.has_key(related_field.name):
            #f.fields[key].fields[related_field.name] = poobrains.form.fields.Value(value=instance.id) # FIXME: Won't work with `CompositeKeyField`s
            #setattr(f.fields[key], related_field.name, poobrains.form.fields.Value(value=instance.id)) # FIXME: Won't work with `CompositeKeyField`s
            setattr(f.fields[key], related_field.name, poobrains.form.fields.Value(value=instance._get_pk_value()))
        else:
            poobrains.app.logger.debug("We need that 'if' after all! Do we maybe have a CompositeKeyField primary key in %s?" % self.related_model.__name__)
            
        f.controls['reset'] = poobrains.form.Button('reset', label='Reset')
        f.controls['submit'] = poobrains.form.Button('submit', name='submit', value='submit', label='Save')

        return f

    
    def __init__(self, related_model, related_field, instance, handle=None, prefix=None, name=None, title=None, method=None, action=None):
        super(RelatedForm, self).__init__(prefix=None, name=None, title=None, method=None, action=None)

        self.instance = instance
        self.related_model = related_model
        self.related_field = related_field

   
#    @poobrains.helpers.themed
#    def view(self, mode='teaser'):
#
#        """
#        view function to be called in a flask request context
#        """
#        if flask.request.method == self.method:
#
#            values = flask.request.form[self.name]
#
#            for field in self:
#
#                if not field.empty():
#                    try:
#                        field.validate(values[field.name])
#
#                        try:
#
#                            field.bind(values[field.name])
#
#                            if isinstance(field, poobrains.form.Fieldset) and not field.errors:
#                                field.handle()
#                                flask.flash("Handled %s.%s" % (field.prefix, field.name))
#                            else:
#                                flask.flash("Not handled:")
#                                flask.flash(field.empty())
#
#
#                        except poobrains.form.errors.BindingError as e:
#                            flask.flash(e.message)
#
#                    except (poobrains.form.errors.ValidationError, poobrains.form.errors.CompoundError) as e:
#                        flask.flash(e.message)
#
#                try:
#                    field.bind(values[field.name]) # bind to show erroneous values to user
#                except poobrains.form.errors.BindingError as e:
#                    flask.flash(e.message)
#
#
#        return self
   

    def handle(self):

        for field in self.fields.itervalues():
            if isinstance(field, poobrains.form.Fieldset):
                field.handle()
        return flask.redirect(flask.request.url)


class UserPermissionAddForm(poobrains.form.AddForm):

    
    def __new__(cls, model_or_instance, mode='add', prefix=None, name=None, title=None, method=None, action=None):

        f = super(UserPermissionAddForm, cls).__new__(cls, model_or_instance, prefix=prefix, name=name, title=title, method=method, action=action)
        del(f.fields['access'])

        return f


    def handle(self):
        return self

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

    #FIXME: causes a zillion fucking SELECT queries

    def __new__(cls, related_model, related_field, instance, name=None, title=None, method=None, action=None):

        f = super(UserPermissionRelatedForm, cls).__new__(cls, related_model, related_field, instance, name=name, title=title, method=method, action=action)

        f.fields.clear() # probably not the most efficient way to have proper form setup without the fields
        for name, perm in Permission.children_keyed().iteritems():

            try:
                perm_info = UserPermission.get(UserPermission.user == instance, UserPermission.permission == name)
                perm_mode = 'edit'

                #f.fields[name] = poobrains.form.EditFieldset(perm_info, mode=perm_mode, name=name)
                #f.fields[name] = perm_info.fieldset_edit(mode=perm_mode)
                fieldset = perm_info.fieldset_edit(mode=perm_mode)
                fieldset.fields['permission'].readonly = True
                fieldset.fields['access'].choices = perm.choices
                fieldset.fields['access'].value = perm_info.access

            except:
                perm_info = UserPermission()
                perm_info.user = instance
                perm_info.permission = name
                perm_info.access = None
                perm_mode = 'add'

                #f.fields[name] = poobrains.form.AddFieldset(perm_info, mode=perm_mode, name=name)
                #f.fields[name] = perm_info.fieldset_add(mode=perm_mode)
                fieldset = perm_info.fieldset_add(mode=perm_mode)
                fieldset.fields['access'].choices = perm.choices

            fieldset.fields.user = poobrains.form.fields.Value(instance)
            fieldset.fields.permission = poobrains.form.fields.Text(value=name, readonly=True)
            setattr(f, name, fieldset)

        return f


#    def handle(self):
#        self.instance.permissions.clear()
#        for perm_fieldset in self.fields.itervalues():
#            if perm_fieldset.fields['access'].value:
#                self.instance.permissions[perm_fieldset.fields['permission'].value] = perm_fieldset.fields['access'].value

        #response = super(UserPermissionRelatedForm, self).handle()

#        for name, perm in Permission.children_keyed().items()
#        return flask.redirect(flask.request.url)


#class BaseAdministerable(poobrains.storage.BaseModel, PermissionInjection):
class BaseAdministerable(PermissionInjection, poobrains.storage.BaseModel):

    """
    Metaclass for `Administerable`s.
    """
    pass
#    def __new__(cls, name, bases, attrs):
#
#        cls = super(BaseAdministerable, cls).__new__(cls, name, bases, attrs)
#
#        perm_attrs = {}
#        if hasattr(cls, '_meta') and hasattr(cls._meta, 'abstract') and cls._meta.abstract:
#
#            class Meta:
#                abstract = True
#
#            perm_attrs['Meta'] = Meta # Makes Permissions for abstract Administerables abstract, too
#
#        #cls.Create = type('%sCreate' % name, (Permission,), perm_attrs)
#        #cls.Read   = type('%sRead' % name, (Permission,), perm_attrs)
#        #cls.Update = type('%sUpdate' % name, (Permission,), perm_attrs)
#        #cls.Delete = type('%sDelete' % name, (Permission,), perm_attrs)
#
#        return cls


class Protected(poobrains.rendering.Renderable):

    __metaclass__ = PermissionInjection

    class Meta:
        abstract = True
        permission_class = Permission


    def __new__(instance, *args, **kwargs):

        instance = super(Protected, instance).__new__(instance, *args, **kwargs)
        instance.permissions = collections.OrderedDict()
        
        for mode, perm_class in instance.__class__.permissions.iteritems():
            instance.permissions[mode] = perm_class(instance)
        return instance



    @protected
    def render(self, mode):
        return super(Protected, self).render(mode)


class Administerable(poobrains.storage.Storable, Protected):
    
    __metaclass__ = BaseAdministerable

    form_add = poobrains.form.AddForm # TODO: move form_ into class Meta?
    form_edit = poobrains.form.EditForm
    form_delete = poobrains.form.DeleteForm

    fieldset_add = poobrains.form.AddFieldset
    fieldset_edit = poobrains.form.EditFieldset
    #fieldset_delete = poobrains.form.DeleteFieldset doesn't yet exist, and isn't used.

    related_form = RelatedForm # TODO: make naming consistent

    class Meta:
        abstract = True
        permission_class = Permission 
        modes = ['full', 'teaser', 'add', 'edit', 'delete']
    
    @property
    def actions(self):

        try:
            self._get_pk_value()
        #except self.__class__.DoesNotExist:
        except peewee.DoesNotExist: # matches both cls.DoesNotExist and ForeignKey related models DoesNotExist
            return poobrains.rendering.RenderString('No actions')

        actions = poobrains.rendering.Menu('%s.actions' % self.handle_string)
#        try:
#            actions.append(self.url('full'), 'View')
#
#        except LookupError:
#            poobrains.app.logger.debug("Couldn't create view link for %s" % self.handle_string)
#
#        try:
#            actions.append(self.url('edit'), 'Edit')
#
#        except LookupError:
#            poobrains.app.logger.debug("Couldn't create edit link for %s" % self.handle_string)
#
#        try:
#            actions.append(self.url('delete'), 'Delete')
#
#        except LookupError:
#            poobrains.app.logger.debug("Couldn't create delete link for %s" % self.handle_string)

        for mode in self.__class__._meta.modes:

            try:
                actions.append(self.url(mode), mode)

            except Exception:
                poobrains.app.logger.debug("Couldn't create %s link for %s" % (mode, self.handle_string))

        return actions


    def form(self, mode=None):
        
        n = 'form_%s' % mode
        if not hasattr(self, n):
            raise NotImplementedError("Form class %s.%s missing." % (self.__class__.__name__, n))

        form_class = getattr(self, n)
        return form_class(mode=mode)#, name=None, title=None, method=None, action=None)
    

    @classmethod
    def class_view(cls, mode, handle=None):
       
        if mode == 'add':
            instance = cls()
        else:
            instance = cls.load(cls.string_handle(handle))

        return instance.view(mode, handle)


    @protected
    @poobrains.helpers.themed
    def view(self, mode, handle):

        """
        view function to be called in a flask request context
        """

        if mode in ('add', 'edit', 'delete'):

            f = self.form(mode)
            return poobrains.helpers.ThemedPassthrough(f.view('full'))

        return self


class Named(Administerable, poobrains.storage.Named):

    class Meta:
        abstract = True

    @property
    def handle_string(self):
        return self.name


    @classmethod
    def string_handle(self, string):
        return string


    @classmethod
    def load(cls, handle):
        if type(handle) is int: #or (isinstance(handle, basestring) and handle.isdigit()):
            return super(Administerable, cls).load(handle)

        else:
            return cls.get(cls.name == handle)


class User(Named):

    #name = poobrains.storage.fields.CharField(unique=True)
    groups = None
    own_permissions = None
    _permissions = None # filled by UserPermission.permission ForeignKeyField

    #form = UserForm

    def __init__(self, *args, **kwargs):

        super(User, self).__init__(*args, **kwargs)
        self.own_permissions = collections.OrderedDict()
        self.groups = []


    def prepared(self):

        for up in self._permissions:
            self.own_permissions[up.permission] = up.access

        for ug in self._groups:
            self.groups.append(ug.group)

    
    def save(self, *args, **kwargs):

        rv = super(User, self).save(*args, **kwargs)

        UserPermission.delete().where(UserPermission.user == self)
        for perm_name, access in self.own_permissions.iteritems():
            up = UserPermission()
            up.user = self
            up.permission = perm_name
            up.access = access
            up.save(force_insert=True)

        UserGroup.delete().where(UserGroup.user == self)
        for group in self.groups:
            ug = UserGroup()
            ug.user = self
            ug.group = group
            ug.save(force_insert=True)

        return rv


class UserPermission(Administerable):

    permission_class = None
    form_add = UserPermissionAddForm
    fieldset_add = UserPermissionAddFieldset
    fieldset_edit = UserPermissionEditFieldset

    class Meta:
        primary_key = peewee.CompositeKey('user', 'permission')
        order_by = ('user', 'permission')

    user = poobrains.storage.fields.ForeignKeyField(User, related_name='_permissions')
    permission = poobrains.storage.fields.CharField(max_length=50)
    access = poobrains.storage.fields.CharField(max_length=4, null=False) #, choices=[(None, 'Ignore'), ('all', 'For all instances'), ('own', 'For own instances'), ('deny', 'Explicitly deny')])
    access.form_class = poobrains.form.fields.TextChoice

    related_form = UserPermissionRelatedForm

    
    def prepared(self):

        try:
            self.permission_class = Permission.children_keyed()[self.permission]

        except KeyError:
            poobrains.app.logger.error("Unknown permission '%s' associated to user #%d." % (self.permission, self.user_id)) # can't use self.user.name because dat recursion
            #TODO: Do we want to do more, like define a permission_class that always denies access?


#    @classmethod
#    def load(cls, id_perm_string):
#
#        (user_id, permission) = id_perm_string.split(',')
#        user = User.load(user_id)
#        return cls.get(cls.user == user, cls.permission == permission)


    def save(self, *args, **kwargs):

        valid_permission_names = []
        for cls in Permission.children():
            valid_permission_names.append(cls.__name__)

        if self.permission not in valid_permission_names:
            raise ValueError("Invalid permission name: %s" % self.permission)

        return super(UserPermission, self).save(*args, **kwargs)

    
    def form(self, mode=None):

        f = super(UserPermission, self).form(mode=mode)

        if mode == 'edit':
            f.fields['access'].choices = self.permission_class.choices 

        return f



class Group(Named):

    # TODO: Almost identical to User. DRY.

    own_permissions = None

    def __init__(self, *args, **kwargs):

        super(Group, self).__init__(*args, **kwargs)
        self.own_permissions = collections.OrderedDict()
        self.groups = collections.OrderedDict()


    def prepared(self):

        for gp in self._permissions:
            self.own_permissions[gp.permission] = gp.access

    
    def save(self, *args, **kwargs):

        rv = super(Group, self).save(*args, **kwargs)

        GroupPermission.delete().where(GroupPermission.group == self)
        for perm_name, access in self.own_permissions.iteritems():
            gp = GroupPermission()
            gp.group = self
            gp.permission = perm_name
            gp.access = access
            gp.save(force_insert=True)

        return rv


class UserGroup(Administerable):

    class Meta:
        primary_key = peewee.CompositeKey('user', 'group')
        order_by = ('user', 'group')

    user = poobrains.storage.fields.ForeignKeyField(User, related_name='_groups')
    group = poobrains.storage.fields.ForeignKeyField(Group, related_name='_users')


class GroupPermission(Administerable):

    class Meta:
        primary_key = peewee.CompositeKey('group', 'permission')
        order_by = ('group', 'permission')

    group = poobrains.storage.fields.ForeignKeyField(Group, null=False, related_name='_permissions')
    permission = poobrains.storage.fields.CharField(max_length=50)
    access = poobrains.storage.fields.CharField(max_length=4, null=False) #, choices=[(None, 'Ignore'), ('all', 'For all instances'), ('own', 'For own instances'), ('deny', 'Explicitly deny')])
    access.form_class = poobrains.form.fields.TextChoice



class ClientCertToken(Administerable):

    validity = None
    user = poobrains.storage.fields.ForeignKeyField(User)
    created = poobrains.storage.fields.DateTimeField(default=datetime.datetime.now, null=False)
    token = poobrains.storage.fields.CharField(unique=True)
    # passphrase = poobrains.storage.fields.CharField(null=True) # TODO: Find out whether we can pkcs#12 encrypt client certs with a passphrase and make browsers still eat it.
    redeemed = poobrains.storage.fields.BooleanField(default=0, null=False)


    def __init__(self, *args, **kw):

        self.validity = poobrains.app.config['TOKEN_VALIDITY']
        super(ClientCertToken, self).__init__(*args, **kw)

    @property
    def redeemable(self):
        return (not self.redeemed) and ((self.created + datetime.timedelta(seconds=self.validity)) < datetime.datetime.now())


class ClientCert(Administerable):

    form_blacklist = ['id', 'user', 'subject_name']

    user = poobrains.storage.fields.ForeignKeyField(User)
    subject_name = poobrains.storage.fields.CharField()



class Owned(Administerable):

    class Meta:
        abstract = True
        permission_class = OwnedPermission


    owner = poobrains.storage.fields.ForeignKeyField(User, null=False)
    owner_mode = poobrains.storage.fields.CharField(null=False, default='')
    group = poobrains.storage.fields.ForeignKeyField(Group, null=False)
    group_mode = poobrains.storage.fields.CharField(null=False, default='')


class NamedOwned(Owned, Named):
    
    class Meta:
        abstract = True
