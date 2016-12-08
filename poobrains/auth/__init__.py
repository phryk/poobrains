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


class PermissionDenied(werkzeug.exceptions.Forbidden):
    status_code = 403


class Permission(poobrains.helpers.ChildAware):
   
    instance = None
    op = None
    label = None
    choices = [('grant', 'Grant'), ('deny', 'Explicitly deny')]

    class Meta:
        abstract = True

    def __init__(self, instance):
        self.instance = instance
        self.check = self.instance_check
        #self.mode = self.__class__.__name__.split('_')[-1] # TODO: Will this explode in my face? Are non-bound permissions going to be a thing?
        # ↑ shouldn't even be needed with PermissionInjection

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
    
    
    @classmethod
    def list(cls, protected, op, user, handles=None):

        q = protected.select()

        if user.own_permissions.has_key(cls.__name__):
            access = user.own_permissions[cls.__name__]

            if access == 'deny':
                raise PermissionDenied("YOU SHALL NOT PASS!")
            elif access == 'grant':
                return q
        
        # check if user is member of any groups with 'deny' for this permission
        group_deny = GroupPermission.select().join(Group).join(UserGroup).join(User).where(UserGroup.user == user, GroupPermission.permission == cls.__name__, GroupPermission.access == 'deny').count()

        if group_deny:
            raise PermissionDenied("YOU SHALL NOT PASS!")

        group_grant = GroupPermission.select().join(Group).join(UserGroup).join(User).where(UserGroup.user == user, GroupPermission.permission == cls.__name__, GroupPermission.access == 'grant').count()

        if group_grant:
            return q


        raise PermissionDenied("YOU SHALL NOT PASS!")


class PermissionInjection(poobrains.helpers.MetaCompatibility):

    def __new__(cls, name, bases, attrs):
        
        cls = super(PermissionInjection, cls).__new__(cls, name, bases, attrs)
        #cls._meta.permissions = collections.OrderedDict()
        cls.permissions = collections.OrderedDict()

        for op, op_name in cls._meta.ops.iteritems():
            perm_name = "%s_%s" % (cls.__name__, op_name)
            perm_label = "%s %s" % (op_name.capitalize(), cls.__name__)
            #cls._meta.permissions[mode] = type(perm_name, (cls._meta.permission_class,), {})
            perm_attrs = dict()
            perm_attrs['op'] = op

            if hasattr(cls._meta, 'abstract') and cls._meta.abstract:

                # Make permissions belonging to abstract Renderables abstract as well
                #FIXME: I have no clue why both _meta and Meta are needed, grok it, simplify if sensible

                meta = poobrains.helpers.FakeMetaOptions()
                meta.abstract = True
                perm_attrs['_meta'] = meta

                class Meta:
                    abstract = True

                perm_attrs['Meta'] = Meta

            cls.permissions[op_name] = type(perm_name, (cls._meta.permission_class,), perm_attrs)

        return cls


#def get_permission(permission_name):
#
#    for perm in Permission.children():
#        if permission_name == perm.__name__:
#            return perm
#
#    raise LookupError("Unknown permission: %s" % str(permission_name))


class FormPermissionField(poobrains.form.fields.Choice):

    default = (None, None)

    def __init__(self, *args, **kwargs):

        super(FormPermissionField, self).__init__(*args, **kwargs)

        self.choices = []
        for perm_name, perm in Permission.children_keyed().iteritems():
            self.choices.append(([('%s.%s' % (perm_name, value), label) for (value, label) in perm.choices], perm_name))


    def validate(self):
        permission, access = self.value

        if not permission in Permission.children_keyed().keys():
            raise poobrains.form.errors.ValidationError('Unknown permission: %s' % permission)

        perm_class = Permission.children_keyed()[permission]
        choice_values = [t[0] for t in perm_class.choices]
        if not access in choice_values:
            raise poobrains.form.errors.ValidationError("Unknown access mode '%s' for permission '%s'." % (access, permission))

    
    def coercer(self, value):

        cleaned_string = poobrains.form.coercers.coerce_string(self, value)

        try:
            permission, access = cleaned_string.split('.')
        except Exception as e:
            raise poobrains.form.errors.ValidationError('Could not split value to permission and access: %s' % cleaned_string)

        return (permission, access)
    

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
    def substitute(cls_or_instance, mode=None, *args, **kwargs):
    #def substitute(cls_or_instance, mode, *args, **kwargs):

        poobrains.app.logger.debug('protected call cls_or_instance: %s, %s', cls_or_instance, dir(cls_or_instance))

        #if not kwargs.has_key('mode'):
        #    raise Exception('Need explicit mode in @protected.')
        #mode = kwargs['mode']
        if not mode:
            raise Exception('Need explicit mode in @protected.')

        user = flask.g.user # FIXME: How do I get rid of the smell?
        if isinstance(cls_or_instance, object):
            cls = cls_or_instance.__class__
        else: # might actually be old style objects, but I'll ignore that for now :F
            cls = cls_or_instance

        if not (issubclass(cls, Protected) or isinstance(cls_or_instance, Protected)):
            raise ValueError("@protected used with non-protected class '%s'." % cls.__name__)

        if not cls._meta.modes.has_key(mode):
            raise PermissionDenied("Unknown mode '%s' for accessing %s." % (mode, cls.__name__))

        op = cls._meta.modes[mode]
        op_name = cls._meta.ops[op]
        if not cls._meta.ops.has_key(op):
            raise PermissionDenied("Unknown access op '%s' for accessing %s." (op, cls.__name__))
        if not cls_or_instance.permissions.has_key(op_name):
            raise NotImplementedError("Did not find permission for op '%s' in cls_or_instance of class '%s'." % (op, cls.__name__))
        

        cls_or_instance.permissions[op_name].check(user)

        #return func(cls_or_instance, *args, **kwargs)
        return func(cls_or_instance, mode=mode, *args, **kwargs)

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
            # creation time older than this means token is dead.
            deathwall = datetime.datetime.now() - datetime.timedelta(seconds=poobrains.app.config['TOKEN_VALIDITY'])

            token = ClientCertToken.get(
                ClientCertToken.token == self.fields['token'].value,
                ClientCertToken.created > deathwall,
                ClientCertToken.redeemed == 0
            )

        except peewee.DoesNotExist as e:
            return poobrains.rendering.RenderString("No such token.")


        try:

            ca_key = M2Crypto.EVP.load_key(poobrains.app.config['CA_KEY'])
            ca_cert = M2Crypto.X509.load_cert(poobrains.app.config['CA_CERT'])

        except Exception as e:

            poobrains.app.logger.error("Client certificate could not be generated. Invalid CA_KEY or CA_CERT.")
            poobrains.app.logger.debug(e)
            return poobrains.rendering.RenderString("Plumbing issue. Invalid CA_KEY or CA_CERT.")


        try:
            common_name = '%s:%s' % (token.user.name, token.cert_name)
            spkac = pyspkac.SPKAC(self.fields['key'].value, flask.session['key_challenge'], CN=common_name) # TODO: Make sure CN is unique
            spkac.push_extension(M2Crypto.X509.new_extension('keyUsage', 'digitalSignature, keyEncipherment, keyAgreement', critical=True))
            spkac.push_extension(M2Crypto.X509.new_extension('extendedKeyUsage', 'clientAuth, emailProtection, nsSGC'))

            spkac.subject.C = ca_cert.get_subject().C

            not_before = int(time.time())
            not_after = not_before + poobrains.app.config['CERT_LIFETIME']

            serial = int(time.time())

            client_cert = spkac.gen_crt(ca_key, ca_cert, serial, not_before, not_after, hash_algo='sha512')
            del flask.session['key_challenge']

        except Exception as e:

            if poobrains.app.debug:
                raise

            return poobrains.rendering.RenderString("Client certificate creation failed.")

        try:
            cert_info = ClientCert()
            cert_info.name = token.name
            cert_info.user = token.user
            cert_info.name = token.cert_name
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
    choices = [
        ('deny', 'Explicitly deny'),
        ('own_instance', 'By instance access mode (own only)'),
        ('instance', 'By instance access mode'),
        ('own', 'For own instances'),
        ('grant', 'For all instances')
    ]
    
    class Meta:
        abstract = True

    @classmethod
    def check(cls, user):

        if user.own_permissions.has_key(cls.__name__):
            access = user.own_permissions[cls.__name__]

            if access == 'deny':
                raise PermissionDenied("YOU SHALL NOT PASS!")

            elif access in ('own_instance', 'instance', 'own', 'grant'):
                return True

            else:
                poobrains.app.logger.warning("Unknown access mode '%s' for User %d with Permission %s" % (access, user.id, cls.__name__))
                raise PermissionDenied("YOU SHALL NOT PASS!")


    def instance_check(self, user):
        
        if user.own_permissions.has_key(self.__class__.__name__):

            access = user.own_permissions[self.__class__.__name__]

            if access == 'deny':
                raise PermissionDenied("YOU SHALL NOT PASS!")

            elif access == 'own_instance':
                if self.instance.owner == user and self.op in self.instance.access:
                    return True
                else:
                    raise PermissionDenied("YOU SHALL NOT PASS!")

            elif access == 'instance':
                if self.op in self.instance.access:
                    return True
                else:
                    raise PermissionDenied("YOU SHALL NOT PASS!")

            elif access == 'own':
                if self.instance.owner == user and self.op in self.instance.access:
                    return True
                else:
                    raise PermissionDenied("YOU SHALL NOT PASS!")

            elif access == 'grant':
                return True

            else:
                raise PermissionDenied("YOU SHALL NOT PASS!")

        else:

            group_access = collections.OrderedDict()
            for group in user.groups:
                if group.own_permissions.has_key(self.__class__.__name__):
                    access = group.own_permissions[self.__class__.__name__]
                    if not group_access.has_key(access):
                        group_access[access] = []
                    group_access[access].append(group)

            if 'deny' in  group_access.keys():
                raise PermissionDenied("YOU SHALL NOT PASS!")

            elif 'own_instance' in group_access.keys():
                allowed_groups = group_access['own_instance']
                if self.instance.group in allowed_groups and self.op in self.instance.access:
                    return True
                else:
                    raise PermissionDenied("YOU SHALL NOT PASS!")

            elif 'instance' in group_access.keys():
                if self.op in self.instance.access:
                    return True
                else:
                    raise PermissionDenied("YOU SHALL NOT PASS!")

            elif 'own' in group_access.keys():
                allowed_groups = group_access['own']
                if self.instance.group in allowed_groups:
                    return True
                else:
                    raise PermissionDenied("YOU SHALL NOT PASS!")

            elif 'grant' in group_access.keys():
                return True

        raise PermissionDenied("YOU SHALL NOT PASS!") # Implicit denial

    
    @classmethod
    def list(cls, protected, op, user): # FIXME: should op be implied, not directly passed?

        cls.check(user) # make sure the user is permitted to get a listing
        q = protected.select()

        if user.own_permissions.has_key(cls.__name__):

            access = user.own_permissions[cls.__name__]
            if access == 'deny':
                raise PermissionDenied("YOU SHALL NOT PASS!")

            elif access == 'own_instance':
                return q.where(protected.owner == user, protected.access.contains(op))
            
            elif access == 'own':
                return q.where(protected.owner == user)

            elif access == 'grant':
                return q

        else:

            group_access = collections.OrderedDict()
            for group in user.groups:
                if group.own_permissions.has_key(cls.__name__):
                    access = group.own_permissions[cls.__name__]
                    if not group_access.has_key(access):
                        group_access[access] = []
                    group_access[access].append(group)

            if 'deny' in  group_access.keys():
                raise PermissionDenied("YOU SHALL NOT PASS!")

            elif 'own_instance' in group_access.keys():
                allowed_groups = group_access['own_instance']
                return q.where(protected.group.in_(allowed_groups), protected.access.contains(op))

            elif 'own' in group_access.keys():
                allowed_groups = group_access['own']
                return q.where(protected.group.in_(allowed_groups))

            elif 'grant' in group_access.keys():
                return q

        raise PermissionDenied("YOU SHALL NOT PASS!") # implicit denial


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
        key = '%s-add' % related_model.__name__

        #f.fields[key] = poobrains.form.AddFieldset(related_instance)
        setattr(f, key, related_instance.fieldset_add())

        if f.fields[key].fields.has_key(related_field.name):
            #f.fields[key].fields[related_field.name] = poobrains.form.fields.Value(value=instance.id) # FIXME: Won't work with `CompositeKeyField`s
            #setattr(f.fields[key], related_field.name, poobrains.form.fields.Value(value=instance.id)) # FIXME: Won't work with `CompositeKeyField`s
            setattr(f.fields[key], related_field.name, poobrains.form.fields.Value(value=instance._get_pk_value()))
        else:
            poobrains.app.logger.debug("We need that 'if' after all! Do we maybe have a CompositeKeyField primary key in %s?" % related_model.__name__)
            
        f.controls['reset'] = poobrains.form.Button('reset', label='Reset')
        f.controls['submit'] = poobrains.form.Button('submit', name='submit', value='submit', label='Save')
        poobrains.app.debugger.set_trace()

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
        if not self.readonly:
            for field in self.fields.itervalues():
                if isinstance(field, poobrains.form.Fieldset):
                    field.handle()
            #return flask.redirect(flask.request.url)
        return self


class UserPermissionAddForm(poobrains.form.AddForm):

    
    def __new__(cls, model_or_instance, mode='add', prefix=None, name=None, title=None, method=None, action=None):

        f = super(UserPermissionAddForm, cls).__new__(cls, model_or_instance, prefix=prefix, name=name, title=title, method=method, action=action)
        del(f.fields['access'])
        del(f.fields['permission'])
        f.permission = FormPermissionField()

        return f


    def handle(self):

        self.instance.user = self.fields['user'].value
        self.instance.permission = self.fields['permission'].value[0]
        self.instance.access = self.fields['permission'].value[1]
        if self.mode == 'add':
            self.instance.save(force_insert=True)
            return flask.redirect(self.instance.url('edit'))
        else:
            self.instance.save()
        return self


class UserPermissionAddFieldset(UserPermissionAddForm, poobrains.form.Fieldset):

    def empty(self):
        rv = self.fields['permission'].empty()
        return rv


class UserPermissionEditFieldset(poobrains.form.EditFieldset):

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


class GroupPermissionAddForm(poobrains.form.AddForm):

    
    def __new__(cls, model_or_instance, mode='add', prefix=None, name=None, title=None, method=None, action=None):

        f = super(GroupPermissionAddForm, cls).__new__(cls, model_or_instance, prefix=prefix, name=name, title=title, method=method, action=action)
        del(f.fields['access'])
        del(f.fields['permission'])
        f.permission = FormPermissionField()

        return f


    def handle(self):

        self.instance.group = self.fields['group'].value
        self.instance.permission = self.fields['permission'].value[0]
        self.instance.access = self.fields['permission'].value[1]
        if self.mode == 'add':
            self.instance.save(force_insert=True)
            return flask.redirect(self.instance.url('edit'))
        else:
            self.instance.save()
        return self


class GroupPermissionEditForm(poobrains.form.EditForm):

    def __new__(cls, model_or_instance, *args, **kwargs):

        f = super(GroupPermissionEditForm, cls).__new__(cls, model_or_instance, *args, **kwargs)
        f.fields['permission'].choices = f.instance.permission_class.choices

        return f


class GroupPermissionAddFieldset(GroupPermissionAddForm, poobrains.form.Fieldset):

    def empty(self):
        rv = self.fields['permission'].empty()
        return rv


class GroupPermissionEditFieldset(poobrains.form.EditForm, poobrains.form.Fieldset):

    def __new__(cls, model_or_instance, mode='edit', prefix=None, name=None, title=None, method=None, action=None):
        return super(GroupPermissionEditFieldset, cls).__new__(cls, model_or_instance, mode=mode, prefix=prefix, name=name, title=title, method=method, action=action)
   

    def __init__(self, model_or_instance, mode='edit', prefix=None, name=None, title=None, method=None, action=None):
        super(GroupPermissionEditFieldset, self).__init__(model_or_instance, mode=mode, prefix=prefix, name=name, title=title, method=method, action=action)



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
    def render(self, mode='full'):
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
        ops = collections.OrderedDict([
            ('c', 'create'),
            ('r', 'read'),
            ('u', 'update'),
            ('d', 'delete')
        ])

        modes = collections.OrderedDict([
            ('add', 'c'),
            ('teaser', 'r'),
            ('full', 'r'),
            ('edit', 'u'),
            ('delete', 'd')
        ])
   

    @property
    def actions(self):

        try:
            self._get_pk_value()
        #except self.__class__.DoesNotExist:
        except peewee.DoesNotExist: # matches both cls.DoesNotExist and ForeignKey related models DoesNotExist
            return poobrains.rendering.RenderString('No actions')

        user = flask.g.user
        actions = poobrains.rendering.Menu('%s.actions' % self.handle_string)

        for mode in self.__class__._meta.modes:

            try:
                op = self._meta.modes[mode]
                op_name = self._meta.ops[op]

                self.permissions[op_name].check(user)

                actions.append(self.url(mode), mode)

            except PermissionDenied:
                poobrains.app.logger.debug("Not generating %s link for %s %s because this user is not authorized for it." % (mode, self.__class__.__name__, self.handle_string))
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
    def class_view(cls, mode=None, handle=None):
       
        if mode == 'add':
            instance = cls()
        else:
            instance = cls.load(cls.string_handle(handle))

        return instance.view(mode=mode, handle=handle)


    @protected
    @poobrains.helpers.themed
    def view(self, mode=None, handle=None):

        """
        view function to be called in a flask request context
        """
        if mode in ('add', 'edit', 'delete'):

            f = self.form(mode)
            return poobrains.helpers.ThemedPassthrough(f.view('full'))

        return self


    @classmethod
    def list(cls, op, user, handles=None):
        op_name = cls._meta.ops[op]
        return cls.permissions[op_name].list(cls, op, user)


class Named(Administerable, poobrains.storage.Named):

    class Meta:
        abstract = True
        handle_fields = ['name']

    #@property
    #def handle_string(self):
    #    return self.name


    #@classmethod
    #def string_handle(self, string):
    #    return string


#    @classmethod
#    def load(cls, handle):
#        if type(handle) is int: #or (isinstance(handle, basestring) and handle.isdigit()):
#            return super(Administerable, cls).load(handle)
#
#        else:
#            return cls.get(cls.name == handle)


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
    access = poobrains.storage.fields.CharField(max_length=4, null=False)
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

    form_add = GroupPermissionAddForm
    form_edit = GroupPermissionEditForm
    fieldset_add = GroupPermissionAddFieldset
    fieldset_edit = GroupPermissionEditFieldset
    permission_class = None

    class Meta:
        primary_key = peewee.CompositeKey('group', 'permission')
        order_by = ('group', 'permission')

    group = poobrains.storage.fields.ForeignKeyField(Group, null=False, related_name='_permissions')
    permission = poobrains.storage.fields.CharField(max_length=50)
    access = poobrains.storage.fields.CharField(max_length=4, null=False)
    access.form_class = poobrains.form.fields.TextChoice

    
    def prepared(self):

        try:
            self.permission_class = Permission.children_keyed()[self.permission]

        except KeyError:
            poobrains.app.logger.error("Unknown permission '%s' associated to user #%d." % (self.permission, self.group_id)) # can't use self.group.name because dat recursion
            #TODO: Do we want to do more, like define a permission_class that always denies access?


    def form(self, mode=None):

        f = super(GroupPermission, self).form(mode=mode)

        if mode == 'edit':
            f.fields['access'].choices = self.permission_class.choices 

        return f


class ClientCertToken(Administerable):

    validity = None
    user = poobrains.storage.fields.ForeignKeyField(User)
    created = poobrains.storage.fields.DateTimeField(default=datetime.datetime.now, null=False)
    cert_name = poobrains.storage.fields.CharField(null=False, max_length=32)
    token = poobrains.storage.fields.CharField(unique=True, default=poobrains.helpers.random_string_light)
    token.form_class = poobrains.form.fields.Value
    # passphrase = poobrains.storage.fields.CharField(null=True) # TODO: Find out whether we can pkcs#12 encrypt client certs with a passphrase and make browsers still eat it.
    redeemed = poobrains.storage.fields.BooleanField(default=0, null=False)


    def __init__(self, *args, **kw):

        self.validity = poobrains.app.config['TOKEN_VALIDITY']
        super(ClientCertToken, self).__init__(*args, **kw)

    @property
    def redeemable(self):
        return (not self.redeemed) and ((self.created + datetime.timedelta(seconds=self.validity)) < datetime.datetime.now())

    def save(self, force_insert=False, only=None):

        if not self.id or force_insert:

            user_token_count = self.__class__.select().where(self.__class__.user == self.user).count()

            if user_token_count >= poobrains.app.config['MAX_TOKENS']:
                raise ValueError( # TODO: Is ValueError really the most fitting exception there is?
                    "User %s already has %d out of %d client certificate tokens." % (
                        self.user.name,
                        user_token_count,
                        poobrains.app.config['MAX_TOKENS']
                    )
                )

            if self.__class__.select().where(self.__class__.user == self.user, self.__class__.cert_name == self.cert_name).count():
                raise ValueError("User %s already has a client certificate token for a certificate named '%s'." % (self.user.name, self.cert_name))

            if ClientCert.select().where(ClientCert.user == self.user, ClientCert.name == self.cert_name).count():
                raise ValueError("User %s already has a client certificate named '%s'." % (self.user.name, self.cert_name))

        return super(ClientCertToken, self).save(force_insert=force_insert, only=only)


class ClientCert(poobrains.storage.Storable):

    user = poobrains.storage.fields.ForeignKeyField(User)
    name = poobrains.storage.fields.CharField(null=False, max_length=32)
    subject_name = poobrains.storage.fields.CharField()
    
    
    def save(self, force_insert=False, only=None):

        if not self.id or force_insert:
            if self.__class__.select().where(self.__class__.user == self.user, self.__class__.name == self.name).count():
                raise ValueError("User %s already has a client certificate named '%s'." % (self.user.name, self.name))

        return super(ClientCert, self).save(force_insert=force_insert, only=only)


class Owned(Administerable):

    class Meta:
        abstract = True
        permission_class = OwnedPermission


    owner = poobrains.storage.fields.ForeignKeyField(User, null=False)
    group = poobrains.storage.fields.ForeignKeyField(Group, null=True)
    access = poobrains.storage.fields.CharField(null=True)


class NamedOwned(Owned, Named):
    
    class Meta:
        abstract = True
