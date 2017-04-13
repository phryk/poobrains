# -*- coding: utf-8 -*-

# external imports
import functools
import collections
import os
import re
import OpenSSL as openssl
import M2Crypto
import pyspkac
import time
import datetime
import werkzeug
import flask
import peewee


# local imports
import poobrains

@poobrains.app.before_first_request
def admin_setup():

    if not poobrains.app._got_first_request:

        administerables = Administerable.children_keyed()

        for key in sorted(administerables):

            cls = administerables[key]

            rule = '%s' % key.lower()
            actions = functools.partial(admin_listing_actions, cls)

            poobrains.app.admin.add_listing(cls, rule, title=cls.__name__, mode='teaser', action_func=actions, force_secure=True)

            if cls._meta.modes.has_key('add'):
                poobrains.app.admin.add_view(cls, os.path.join(rule, 'add/'), mode='add', force_secure=True)

            rule = os.path.join(rule, '<handle>/')

            if cls._meta.modes.has_key('edit'):
                poobrains.app.admin.add_view(cls, rule, mode='edit', force_secure=True)

            if cls._meta.modes.has_key('delete'):
                poobrains.app.admin.add_view(cls, os.path.join(rule, 'delete'), mode='delete', force_secure=True)

            for related_field in cls._meta.reverse_rel.itervalues(): # Add Models that are associated by ForeignKeyField, like /user/foo/userpermissions
                related_model = related_field.model_class

                if issubclass(related_model, Administerable):
                    poobrains.app.admin.add_related_view(cls, related_field, rule, force_secure=True)

        

        #poobrains.app.register_blueprint(poobrains.app.admin, url_prefix='/admin/')


@poobrains.app.admin.before_request
def checkAAA():

    try:
        AccessAdminArea.check(flask.g.user)
    except AccessDenied:
        raise werkzeug.exceptions.NotFound() # Less infoleak fo' shizzle (Unless we display e.message on errorpage)


class AccessDenied(werkzeug.exceptions.Forbidden):
    status_code = 403


class CryptoError(werkzeug.exceptions.InternalServerError):
    status_code = 500


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


    @classmethod
    def check(cls, user):

        # check user-assigned permission state
        if user.own_permissions.has_key(cls.__name__):
            access = user.own_permissions[cls.__name__]

            if access == 'deny':
                raise AccessDenied("YOU SHALL NOT PASS!")

            elif access == 'grant':
                return True

        # check if user is member of any groups with 'deny' for this permission
        group_deny = GroupPermission.select().join(Group).join(UserGroup).join(User).where(UserGroup.user == user, GroupPermission.permission == cls.__name__, GroupPermission.access == 'deny').count()

        if group_deny:
            raise AccessDenied("YOU SHALL NOT PASS!")

        group_grant = GroupPermission.select().join(Group).join(UserGroup).join(User).where(UserGroup.user == user, GroupPermission.permission == cls.__name__, GroupPermission.access == 'grant').count()

        if group_grant:
            return True

        raise AccessDenied("YOU SHALL NOT PASS!")


    def instance_check(self, user):
        return self.__class__.check(user)
    
    
    @classmethod
    def list(cls, protected, q, op, user): # FIXME: should op be implied, not directly passed?

        if user.own_permissions.has_key(cls.__name__):
            access = user.own_permissions[cls.__name__]

            if access == 'deny':
                raise AccessDenied("YOU SHALL NOT PASS!")
            elif access == 'grant':
                return q
        
        # check if user is member of any groups with 'deny' for this permission
        group_deny = GroupPermission.select().join(Group).join(UserGroup).join(User).where(UserGroup.user == user, GroupPermission.permission == cls.__name__, GroupPermission.access == 'deny').count()

        if group_deny:
            raise AccessDenied("YOU SHALL NOT PASS!")

        group_grant = GroupPermission.select().join(Group).join(UserGroup).join(User).where(UserGroup.user == user, GroupPermission.permission == cls.__name__, GroupPermission.access == 'grant').count()

        if group_grant:
            return q


        raise AccessDenied("YOU SHALL NOT PASS!")


class AccessAdminArea(Permission):
    pass


class PermissionInjection(poobrains.helpers.MetaCompatibility):

    def __new__(cls, name, bases, attrs):
        
        cls = super(PermissionInjection, cls).__new__(cls, name, bases, attrs)
        cls.permissions = collections.OrderedDict()

        #for op in ['create', 'read', 'update', 'delete']:
        for op in set(cls._meta.modes.itervalues()):
            perm_name = "%s_%s" % (cls.__name__, op)
            perm_label = "%s %s" % (op.capitalize(), cls.__name__)
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

            cls.permissions[op] = type(perm_name, (cls._meta.permission_class,), perm_attrs)

        return cls


class FormPermissionField(poobrains.form.fields.Choice):

    default = (None, None)

    def __init__(self, *args, **kwargs):
        super(FormPermissionField, self).__init__(*args, **kwargs)

        self.choices = []

        permissions = Permission.children_keyed()
        for perm_name in sorted(permissions):
            perm = permissions[perm_name]
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

    m = poobrains.rendering.Menu('actions')
    if cls._meta.modes.has_key('add'):
        m.append(cls.url('add'), 'add new %s' % (cls.__name__,))

    return m


@poobrains.app.admin.box('menu_main')
def admin_menu():

    try:
        AccessAdminArea.check(flask.g.user) # check if current user may even access the admin area

        menu = poobrains.rendering.Menu('main')
        menu.title = 'Administration'

        for administerable, listings in poobrains.app.admin.listings.iteritems():

            for mode, endpoints in listings.iteritems():

                for endpoint in endpoints: # iterates through endpoints.keys()
                    menu.append(flask.url_for('admin.%s' % endpoint), administerable.__name__)

        return menu

    except AccessDenied:
        return None


@poobrains.app.admin.route('/')
@poobrains.helpers.themed
def admin_index():

    try:

        AccessAdminArea.check(flask.g.user)

        container = poobrains.rendering.Container(title='Administration')
        
        for administerable, listings in poobrains.app.admin.listings.iteritems():

            subcontainer = poobrains.rendering.Container()
            menu = poobrains.rendering.Menu('listings-%s' % administerable.__name__)
            for mode, endpoints in listings.iteritems():

                for endpoint in endpoints: # iterates through endpoints.keys()
                    menu.append(flask.url_for('admin.%s' % endpoint), administerable.__name__)

            subcontainer.append(menu)
            if administerable.__doc__:
                subcontainer.append(poobrains.rendering.RenderString(administerable.__doc__))
            container.append(subcontainer)

        return container

    except AccessDenied:
        return None


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
            raise AccessDenied("Unknown mode '%s' for accessing %s." % (mode, cls.__name__))

        op = cls._meta.modes[mode]
        if not op in ['create', 'read', 'update', 'delete']:
            raise AccessDenied("Unknown access op '%s' for accessing %s." (op, cls.__name__))
        if not cls_or_instance.permissions.has_key(op):
            raise NotImplementedError("Did not find permission for op '%s' in cls_or_instance of class '%s'." % (op, cls.__name__))
        

        cls_or_instance.permissions[op].check(user)

        return func(cls_or_instance, mode=mode, *args, **kwargs)

    return substitute


@poobrains.app.expose('/cert/', force_secure=True)
class ClientCertForm(poobrains.form.Form):

    #passphrase = poobrains.form.fields.ObfuscatedText()
    title = "Be safe, certificatisize yourself!"
    token = poobrains.form.fields.ObfuscatedText(label='Token')
    key = poobrains.form.fields.Keygen()
    keygen_submit = poobrains.form.Button('submit', label='Generate certificate with <keygen>')
    pgp_submit = poobrains.form.Button('submit', label="Generate keypair + certificate and send it via PGP-mail")
    tls_submit = poobrains.form.Button('submit', label="Generate keypair + certificate and send it via HTTPS")

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
            
            flask.flash("No such token.", 'error')
            return flask.redirect(self.url())
            
        cert_info = ClientCert()
        cert_info.user = token.user
        cert_info.name = token.cert_name
        
        if self.controls['keygen_submit'].value:

            try:
                client_cert = token.user.gen_clientcert_from_spkac(token.cert_name, self.fields['key'].value, flask.session['key_challenge'])
                del flask.session['key_challenge']

            except Exception as e: # FIXME: More specific exception matching?

                if poobrains.app.debug:
                    raise

                return poobrains.rendering.RenderString("Client certificate creation failed.")

            cert_info.keylength = client_cert.get_pubkey().size() * 8 # .size gives length in byte
            cert_info.fingerprint = client_cert.get_fingerprint('sha512')

            r = werkzeug.wrappers.Response(client_cert.as_pem())
            r.mimetype = 'application/x-x509-user-cert'

        #elif submit in ('ClientCertForm.pgp_submit', 'ClientCertForm.tls_submit'):
        elif self.controls['pgp_submit'].value or self.controls['tls_submit'].value:

            passphrase = poobrains.helpers.random_string_light()

            try:

                pkcs12 = token.user.gen_keypair_and_clientcert(token.cert_name)


            except Exception as e:
                return poobrains.rendering.RenderString("Client certificate creation failed.")

            cert_info.keylength = pkcs12.get_certificate().get_pubkey().bits() 
            cert_info.fingerprint = pkcs12.get_certificate().digest('sha512').replace(':', '')

            #if submit == 'ClientCertForm.tls_submit':
            if self.controls['tls_submit'].value:
                r = werkzeug.wrappers.Response(pkcs12.export(passphrase=passphrase))
                r.mimetype = 'application/pkcs-12'
                flask.flash("The passphrase for this delicious bundle of crypto is '%s'" % passphrase)

            else: # means pgp

                text = "Hello %s. Here's your new set of keys to the gates of Shambala.\nYour passphrase is '%s'." % (token.user.name, passphrase)

                mail = poobrains.mailing.Mail(token.user.pgp_fingerprint)
                mail['Subject'] = 'Bow before entropy'
                mail['To'] = token.user.mail

                mail.attach(poobrains.mailing.MIMEText(text))
                pkcs12_attachment = poobrains.mailing.MIMEApplication(pkcs12.export(passphrase=passphrase), _subtype='pkcs12')
                mail.attach(pkcs12_attachment)

                mail.send()

                flask.flash("Your private key and client certificate have been send to '%s'." % token.user.mail)

                r = self


        try:
            cert_info.save()

        except Exception as e:

            if poobrains.app.debug:
                raise

            return poobrains.rendering.RenderString("Failed to write info into database. Disregard this certificate.")

        token.redeemed = True
        token.save()

        return r


class OwnedPermission(Permission):

    choices = [
        ('deny', 'Explicitly deny'),
        ('own_instance', 'By instance access mode (own only)'),
        ('instance', 'By instance access mode'),
        ('own', 'For own instances'),
        ('grant', 'For all instances')
    ]

    op_abbreviations = {
        'create': 'c',
        'read': 'r',
        'update': 'u',
        'delete': 'd'
    }
    
    class Meta:
        abstract = True

    @classmethod
    def check(cls, user):

        if user.own_permissions.has_key(cls.__name__):
            access = user.own_permissions[cls.__name__]

            if access == 'deny':
                raise AccessDenied("YOU SHALL NOT PASS!")

            elif access in ('own_instance', 'instance', 'own', 'grant'):
                return True

            else:
                poobrains.app.logger.warning("Unknown access mode '%s' for User %d with Permission %s" % (access, user.id, cls.__name__))
                raise AccessDenied("YOU SHALL NOT PASS!")

        else:

            group_access = cls.group_access(user)
            if 'deny' in group_access.keys():
                raise AccessDenied("YOU SHALL NOT PASS!")

            elif 'own_instance' in group_access.keys() or 'instance' in group_access.keys() or 'own' in group_access.keys() or 'grant' in group_access.keys():
                return True

            else:
                raise AccessDenied("YOU SHALL NOT PASS!")


    def instance_check(self, user):

        op_abbr = self.op_abbreviations[self.op]

        if user.own_permissions.has_key(self.__class__.__name__):

            access = user.own_permissions[self.__class__.__name__]

            if access == 'deny':
                raise AccessDenied("YOU SHALL NOT PASS!")

            elif access == 'own_instance':
                if self.instance.owner == user and op_abbr in self.instance.access:
                    return True
                else:
                    raise AccessDenied("YOU SHALL NOT PASS!")

            elif access == 'instance':
                if op_abbr in self.instance.access:
                    return True
                else:
                    raise AccessDenied("YOU SHALL NOT PASS!")

            elif access == 'own':
                if self.instance.owner == user and op_abbr in self.instance.access:
                    return True
                else:
                    raise AccessDenied("YOU SHALL NOT PASS!")

            elif access == 'grant':
                return True

            else:
                raise AccessDenied("YOU SHALL NOT PASS!")

        else:

            group_access = self.__class__.group_access(user)

            if 'deny' in  group_access.keys():
                raise AccessDenied("YOU SHALL NOT PASS!")

            elif 'own_instance' in group_access.keys():
                allowed_groups = group_access['own_instance']
                if self.instance.group in allowed_groups and op_abbr in self.instance.access:
                    return True
                else:
                    raise AccessDenied("YOU SHALL NOT PASS!")

            elif 'instance' in group_access.keys():
                if op_abbr in self.instance.access:
                    return True
                else:
                    raise AccessDenied("YOU SHALL NOT PASS!")

            elif 'own' in group_access.keys():
                allowed_groups = group_access['own']
                if self.instance.group in allowed_groups:
                    return True
                else:
                    raise AccessDenied("YOU SHALL NOT PASS!")

            elif 'grant' in group_access.keys():
                return True

        raise AccessDenied("YOU SHALL NOT PASS!") # Implicit denial


    @classmethod
    def group_access(cls, user):

        group_access = collections.OrderedDict()
        for group in user.groups:
            if group.own_permissions.has_key(cls.__name__):
                access = group.own_permissions[cls.__name__]
                if not group_access.has_key(access):
                    group_access[access] = []
                group_access[access].append(group)

        return group_access
   

    @classmethod
    def list(cls, protected, q, op, user): # FIXME: should op be implied, not directly passed?

        cls.check(user) # make sure the user is permitted to get a listing

        if user.own_permissions.has_key(cls.__name__):

            access = user.own_permissions[cls.__name__]
            if access == 'deny':
                raise AccessDenied("YOU SHALL NOT PASS!")

            elif access == 'own_instance':
                return q.where(protected.owner == user, protected.access.contains(op))

            elif access == 'instance':
                return q.where(protected.access.contains(op))

            elif access == 'own':
                return q.where(protected.owner == user)

            elif access == 'grant':
                return q

        else:

            group_access = cls.group_access(user)

            if 'deny' in  group_access.keys():
                raise AccessDenied("YOU SHALL NOT PASS!")

            elif 'own_instance' in group_access.keys():
                allowed_groups = group_access['own_instance']
                return q.where(protected.group.in_(allowed_groups), protected.access.contains(op))

            elif 'instance' in group_access.keys():
                return q.where(protected.access.contains(op))

            elif 'own' in group_access.keys():
                allowed_groups = group_access['own']
                return q.where(protected.group.in_(allowed_groups))

            elif 'grant' in group_access.keys():
                return q

        raise AccessDenied("YOU SHALL NOT PASS!") # implicit denial


class RelatedForm(poobrains.form.Form):
   
    instance = None
    related_model = None
    related_field = None

    def __new__(cls, related_model, related_field, instance, name=None, title=None, method=None, action=None):

        related_model.permissions['create'].check(flask.g.user)
        related_model.permissions['update'].check(flask.g.user)
        f = super(RelatedForm, cls).__new__(cls, name=name, title=title, method=method, action=action)

        for related_instance in getattr(instance, related_field.related_name):
            try:

                related_instance.permissions['update'].check(flask.g.user) # throws AccessDenied if user is not authorized
                key = related_instance.handle_string

                # Fieldset to edit an existing related instance of this instance
                setattr(f, key, related_instance.fieldset_edit())

                if f.fields[key].fields.has_key(related_field.name):
                    setattr(f.fields[key], related_field.name, poobrains.form.fields.Value(value=instance._get_pk_value()))

            except AccessDenied as e:
                pass


        try:
            # Fieldset to add a new related instance to this instance
            related_model.permissions['create'].check(flask.g.user)
            related_instance = related_model()
            setattr(related_instance, related_field.name, instance) 
            key = '%s-add' % related_model.__name__

            setattr(f, key, related_instance.fieldset_add())

            if f.fields[key].fields.has_key(related_field.name):
                setattr(f.fields[key], related_field.name, poobrains.form.fields.Value(value=instance._get_pk_value()))
            else:
                poobrains.app.logger.debug("We need that 'if' after all! Do we maybe have a CompositeKeyField primary key in %s?" % related_model.__name__)

        except AccessDenied as e:
            pass
            
        f.controls['reset'] = poobrains.form.Button('reset', label='Reset')
        f.controls['submit'] = poobrains.form.Button('submit', name='submit', value='submit', label='Save')

        return f

    
    def __init__(self, related_model, related_field, instance, handle=None, prefix=None, name=None, title=None, method=None, action=None):
        super(RelatedForm, self).__init__(prefix=None, name=None, title=None, method=None, action=None)

        self.instance = instance
        self.related_model = related_model
        self.related_field = related_field

   
    def handle(self):
        if not self.readonly:
            for field in self.fields.itervalues():
                if isinstance(field, poobrains.form.Fieldset):
                    try:
                        field.handle()
                    except Exception as e:
                        flask.flash("Failed to handle fieldset '%s.%s'." % (field.prefix, field.name))
                        poobrains.app.logger.error("Failed to handle fieldset %s.%s - %s: %s" % (field.prefix, field.name, type(e).__name__, e.message))
                        
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

                fieldset = perm_info.fieldset_add(mode=perm_mode)
                #fieldset.fields['access'].choices = perm.choices

            fieldset.fields.user = poobrains.form.fields.Value(instance)
            fieldset.fields.permission = poobrains.form.fields.Text(value=name, readonly=True)
            setattr(f, name, fieldset)

        return f


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


#class ProtectedForm(Protected, poobrains.form.Form):
#    pass # let's just hope this works out of the box


class Administerable(poobrains.storage.Storable, Protected):
    
    __metaclass__ = BaseAdministerable

    form_add = poobrains.form.AddForm # TODO: move form_ into class Meta?
    form_edit = poobrains.form.EditForm
    form_delete = poobrains.form.DeleteForm

    fieldset_add = poobrains.form.AddFieldset
    fieldset_edit = poobrains.form.EditFieldset

    related_form = RelatedForm # TODO: make naming consistent

    class Meta:
        abstract = True
        related_use_form = False # Whether we want to use Administerable.related_form in related view for administration.
        permission_class = Permission

        modes = collections.OrderedDict([
            ('add', 'create'),
            ('teaser', 'read'),
            ('full', 'read'),
            ('edit', 'update'),
            ('delete', 'delete')
        ])
   

    @property
    def menu_actions(self):
        
        try:
            self._get_pk_value()
        except peewee.DoesNotExist: # matches both cls.DoesNotExist and ForeignKey related models DoesNotExist
            return None

        user = flask.g.user
        actions = poobrains.rendering.Menu('actions')

        for mode in self.__class__._meta.modes:

            try:
                op = self._meta.modes[mode]

                if op != 'create':
                    self.permissions[op].check(user)
                    actions.append(self.url(mode), mode)

            except AccessDenied:
                poobrains.app.logger.debug("Not generating %s link for %s %s because this user is not authorized for it." % (mode, self.__class__.__name__, self.handle_string))
            except Exception:
                poobrains.app.logger.debug("Couldn't create %s link for %s" % (mode, self.handle_string))

        return actions


    @property
    def menu_related(self):

        try:
            self._get_pk_value()
        except peewee.DoesNotExist:
            return None

        user = flask.g.user
        menu = poobrains.rendering.Menu('related')

        for related_field in self._meta.reverse_rel.itervalues(): # Add Models that are associated by ForeignKeyField, like /user/foo/userpermissions
            related_model = related_field.model_class
            if related_model is not self.__class__ and issubclass(related_model, Administerable) and not related_model._meta.abstract:
                try:
                    menu.append(self.related_url(related_field) , related_model.__name__)
                except LookupError:
                    pass
        return menu


    def related_url(self, related_field):
        return poobrains.app.get_related_view_url(self.__class__, self.handle_string, related_field)

    def form(self, mode=None):
        
        n = 'form_%s' % mode
        if not hasattr(self, n):
            raise NotImplementedError("Form class %s.%s missing." % (self.__class__.__name__, n))

        form_class = getattr(self, n)
        return form_class(mode=mode)#, name=None, title=None, method=None, action=None)
    

    @classmethod
    def class_view(cls, mode=None, handle=None, **kwargs):
       
        if mode == 'add':
            instance = cls()
        else:
            try:
                instance = cls.load(cls.string_handle(handle))
            except ValueError:
                raise cls.DoesNotExist("This isn't even the right type!")

        return instance.view(mode=mode, handle=handle, **kwargs)


    @protected
    @poobrains.helpers.themed
    def view(self, mode='teaser', handle=None, **kwargs):

        """
        view function to be called in a flask request context
        """
        
        if self._meta.modes[mode] in ['create', 'update', 'delete']:

            f = self.form(mode)
            return poobrains.helpers.ThemedPassthrough(f.view('full'))

        return self


    @classmethod
    def list(cls, op, user, handles=None):
        q = super(Administerable, cls).list(op, user, handles=handles)
        return cls.permissions[op].list(cls, q, op, user)


    @classmethod
    def related_view(cls, related_field=None, handle=None):

        if related_field is None:
            raise TypeError("%s.related_view needs Field instance for parameter 'related_field'. Got %s (%s) instead." % (cls.__name__, type(field).__name__, unicode(field)))

        related_model = related_field.model_class
        instance = cls.load(cls.string_handle(handle))

        if flask.request.blueprint == 'admin' and related_model._meta.related_use_form:
            if hasattr(related_model, 'related_form'):
                form_class = related_model.related_form
            else:
                form_class = functools.partial(poobrains.auth.RelatedForm, related_model) # TODO: does this even work? and more importantly, is it even needed?

            f = form_class(related_field, instance)
            
            return f.view('full')

        else:
            return poobrains.storage.Listing(
                cls=related_model,
                query=related_model.list('read', flask.g.user).where(related_field == instance)
            ).view()


class Named(Administerable, poobrains.storage.Named):

    class Meta:
        abstract = True
        handle_fields = ['name']


class User(Named):

    groups = None
    own_permissions = None

    mail = poobrains.storage.fields.CharField(null=True) # FIXME: implement an EmailField
    pgp_fingerprint = poobrains.storage.fields.CharField(null=True)
    mail_notifications = poobrains.storage.fields.BooleanField(default=False)
    about = poobrains.md.MarkdownField(null=True)

    def __init__(self, *args, **kwargs):

        super(User, self).__init__(*args, **kwargs)
        self.own_permissions = collections.OrderedDict()
        self.groups = []


    def prepared(self):

        super(User, self).prepared()
        for up in self._permissions:
            self.own_permissions[up.permission] = up.access

        for ug in self._groups:
            self.groups.append(ug.group)

    
    def save(self, *args, **kwargs):

        rv = super(User, self).save(*args, **kwargs)

        UserPermission.delete().where(UserPermission.user == self).execute()
        for perm_name, access in self.own_permissions.iteritems():
            up = UserPermission()
            up.user = self
            up.permission = perm_name
            up.access = access
            up.save(force_insert=True)

        UserGroup.delete().where(UserGroup.user == self).execute()
        for group in self.groups:
            ug = UserGroup()
            ug.user = self
            ug.group = group
            ug.save(force_insert=True)

        return rv


    def gen_clientcert_from_spkac(self, name, spkac, challenge):

        try:

            ca_key = M2Crypto.EVP.load_key(poobrains.app.config['CA_KEY'])
            ca_cert = M2Crypto.X509.load_cert(poobrains.app.config['CA_CERT'])

        except Exception as e:

            poobrains.app.logger.error("Client certificate could not be generated. Invalid CA_KEY or CA_CERT.")
            poobrains.app.logger.debug(e)
            flask.flash("Plumbing issue. Invalid CA_KEY or CA_CERT.")
            raise e

        common_name = '%s:%s@%s' % (self.name, name, poobrains.app.config['SITE_NAME'])
        spkac = pyspkac.SPKAC(spkac, challenge, CN=common_name) # TODO: Make sure CN is unique
        spkac.push_extension(M2Crypto.X509.new_extension('keyUsage', 'digitalSignature, keyEncipherment, keyAgreement', critical=True))
        spkac.push_extension(M2Crypto.X509.new_extension('extendedKeyUsage', 'clientAuth, emailProtection, nsSGC'))

        spkac.subject.C = ca_cert.get_subject().C

        not_before = int(time.time())
        not_after = not_before + poobrains.app.config['CERT_LIFETIME']

        serial = int(time.time())

        return spkac.gen_crt(ca_key, ca_cert, serial, not_before, not_after, hash_algo='sha512')


    def gen_keypair_and_clientcert(self, name):
     
        if not re.match('^[a-zA-Z0-9_\- ]+$', name):
            raise ValueError("Requested client certificate name is invalid.")

        common_name = '%s:%s@%s' % (self.name, name, poobrains.app.config['SITE_NAME'])

        fd = open(poobrains.app.config['CA_KEY'], 'rb')
        ca_key = openssl.crypto.load_privatekey(openssl.crypto.FILETYPE_PEM, fd.read())
        fd.close()
        del fd

        fd = open(poobrains.app.config['CA_CERT'], 'rb')
        ca_cert = openssl.crypto.load_certificate(openssl.crypto.FILETYPE_PEM, fd.read())
        fd.close()
        del fd

        keypair = openssl.crypto.PKey()
        keypair.generate_key(openssl.crypto.TYPE_RSA, 4096)

        extensions = []
        extensions.append(openssl.crypto.X509Extension('keyUsage', True, 'digitalSignature, keyEncipherment, keyAgreement'))
        extensions.append(openssl.crypto.X509Extension('extendedKeyUsage', True, 'clientAuth'))

        cert = openssl.crypto.X509()
        cert.set_version(2) # 2 == 3, WHAT THE FUCK IS WRONG WITH THESE PEOPLE!?
        cert.add_extensions(extensions)
        cert.set_issuer(ca_cert.get_subject())
        cert.set_pubkey(keypair)
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(poobrains.app.config['CERT_LIFETIME'])
        cert.set_serial_number(int(time.time())) # FIXME: This is bad, but probably won't fuck us over for a while ¯\_(ツ)_/¯
        cert.get_subject().CN = common_name
        cert.get_subject().C = ca_cert.get_subject().C

        cert.sign(ca_key, 'sha512')

        pkcs12 = openssl.crypto.PKCS12()
        pkcs12.set_ca_certificates([ca_cert])
        pkcs12.set_privatekey(keypair)
        pkcs12.set_certificate(cert)
        pkcs12.set_friendlyname(str(name))

        return pkcs12


    def mkmail(self):

        mail = poobrains.mailing.Mail()
        mail['To'] = self.mail
        mail['Subject'] = 'Bow before entropy'
        mail.fingerprint = self.pgp_fingerprint

        return mail


    def notify(self, message):
        
        n = Notification(to=self, message=message)

        if self.mail_notifications:
            if not self.pgp_fingerprint:
                n.message += "\nYou didn't get a mail notification because you have no PGP public key stored."

            else:
                mail = self.mkmail()
                mail.attach(poobrains.mailing.MIMEText(message))
                mail.send()

        return n.save()


    @property
    def notifications_unread(self):
        return self.notifications.where(Notification.read == 0)

poobrains.app.site.add_view(User, '/~<handle>/', 'full')

class UserPermission(Administerable):

    permission_class = None
    form_add = UserPermissionAddForm
    fieldset_add = UserPermissionAddFieldset
    fieldset_edit = UserPermissionEditFieldset

    class Meta:
        primary_key = peewee.CompositeKey('user', 'permission')
        order_by = ('user', 'permission')
        related_use_form = True

    user = poobrains.storage.fields.ForeignKeyField(User, related_name='_permissions')
    permission = poobrains.storage.fields.CharField(max_length=50)
    access = poobrains.storage.fields.CharField(null=False)
    access.form_class = poobrains.form.fields.TextChoice

    related_form = UserPermissionRelatedForm

    
    def prepared(self):
        
        super(UserPermission, self).prepared()

        try:
            self.permission_class = Permission.children_keyed()[self.permission]

        except KeyError:
            poobrains.app.logger.error("Unknown permission '%s' associated to user #%d." % (self.permission, self.user_id)) # can't use self.user.name because dat recursion
            #TODO: Do we want to do more, like define a permission_class that always denies access?


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
        
        super(Group, self).prepared()

        for gp in self._permissions:
            self.own_permissions[gp.permission] = gp.access

    
    def save(self, *args, **kwargs):

        rv = super(Group, self).save(*args, **kwargs)

        GroupPermission.delete().where(GroupPermission.group == self).execute()
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
    access = poobrains.storage.fields.CharField(null=False)
    access.form_class = poobrains.form.fields.TextChoice

    
    def prepared(self):

        super(GroupPermission, self).prepared()

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


class ClientCertToken(Administerable, Protected):

    validity = None
    user = poobrains.storage.fields.ForeignKeyField(User, related_name='clientcerttokens')
    created = poobrains.storage.fields.DateTimeField(default=datetime.datetime.now, null=False)
    cert_name = poobrains.storage.fields.CharField(null=False, max_length=32, constraints=[poobrains.storage.RegexpConstraint('cert_name', '^[a-zA-Z0-9_\- ]+$')])
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


class ClientCert(Administerable):

    class Meta:

        permission_class = Permission
        modes = collections.OrderedDict([
            ('teaser', 'read'),
            ('full', 'read'),
            ('delete', 'delete')
        ])

    user = poobrains.storage.fields.ForeignKeyField(User, related_name="clientcerts")
    name = poobrains.storage.fields.CharField(null=False, max_length=32)
    #subject_name = poobrains.storage.fields.CharField()
    keylength = poobrains.storage.fields.IntegerField()
    fingerprint = poobrains.storage.fields.CharField()
    
    
    def save(self, force_insert=False, only=None):

        if not self.id or force_insert:
            if self.__class__.select().where(self.__class__.user == self.user, self.__class__.name == self.name).count():
                raise ValueError("User %s already has a client certificate named '%s'." % (self.user.name, self.name))

        return super(ClientCert, self).save(force_insert=force_insert, only=only)

    
    @protected
    @poobrains.helpers.themed
    def view(self, mode='teaser', handle=None, **kwargs):

        """
        view function to be called in a flask request context
        """
        
        if self._meta.modes[mode] in ['create', 'update', 'delete']:

            f = self.form(mode)
            return poobrains.helpers.ThemedPassthrough(f.view('full'))

        return self


class Owned(Administerable):

    class Meta:
        abstract = True
        permission_class = OwnedPermission


    owner = poobrains.storage.fields.ForeignKeyField(User, null=False)
    group = poobrains.storage.fields.ForeignKeyField(Group, null=True)
    access = poobrains.storage.fields.CharField(default='')

    def form(self, mode=None):

        f = super(Owned, self).form(mode)

        if mode == 'add':
            f.fields['owner'].value = flask.g.user
            f.fields['group'].value = flask.g.user.groups[0]

        return f


class NamedOwned(Owned, Named):
    
    class Meta:
        abstract = True


class Notification(poobrains.storage.Storable):

    to = poobrains.storage.fields.ForeignKeyField(User, related_name='notifications')
    created = poobrains.storage.fields.DateTimeField(default=datetime.datetime.now, null=False)
    read = poobrains.storage.fields.BooleanField(default=False)
    message = poobrains.md.MarkdownField()
