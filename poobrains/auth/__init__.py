# -*- coding: utf-8 -*-

"""
The authentication system.

This module implements permissions/access control and administration functionality.
"""

# external imports
import functools
import collections
import os
import random
import re
import OpenSSL as openssl
import M2Crypto
import pyspkac
import time
import datetime
import werkzeug
import click
import peewee


# local imports
from poobrains import app, Markup, flash, request, session, redirect, url_for, g, locked_cached_property
import poobrains.helpers
import poobrains.errors
import poobrains.mailing
import poobrains.rendering
import poobrains.form
import poobrains.storage
import poobrains.md


@app.before_first_request
def admin_setup():

    if not app._got_first_request:

        administerables = Administerable.class_children_keyed(lower=True)

        for key in sorted(administerables):

            cls = administerables[key]

            rule = key
            actions = functools.partial(admin_listing_actions, cls)

            app.admin.add_listing(cls, rule, title=cls.__name__, mode='teaser', action_func=actions, force_secure=True)

            if cls._meta.modes.has_key('add'):
                app.admin.add_view(cls, os.path.join(rule, 'add/'), mode='add', force_secure=True)

            rule = os.path.join(rule, '<handle>/')

            if cls._meta.modes.has_key('edit'):
                app.admin.add_view(cls, rule, mode='edit', force_secure=True)

            if cls._meta.modes.has_key('delete'):
                app.admin.add_view(cls, os.path.join(rule, 'delete'), mode='delete', force_secure=True)

            for related_model, related_fields in cls._meta.model_backrefs.iteritems(): # Add Models that are associated by ForeignKeyField, like /user/foo/userpermissions

                if issubclass(related_model, Administerable):
                    app.admin.add_related_view(cls, related_fields[0], rule, force_secure=True)


@app.admin.before_request
def checkAAA():

    try:
        AccessAdminArea.check(g.user)
    except AccessDenied:
        raise werkzeug.exceptions.NotFound() # Less infoleak fo' shizzle (Unless we display e.message on errorpage)


class AccessDenied(werkzeug.exceptions.Forbidden):

    status_code = 403
    description = "YOU SHALL NOT PASS!"


class CryptoError(werkzeug.exceptions.InternalServerError):
    status_code = 500


class BoundForm(poobrains.form.Form):

    mode = None
    model = None
    instance = None

    class Meta:
        abstract = True

    def __new__(cls, model_or_instance, mode=None, prefix=None, name=None, title=None, method=None, action=None):

        f = super(BoundForm, cls).__new__(cls, prefix=prefix, name=name, title=title, method=method, action=action)

        if isinstance(model_or_instance, type(Administerable)): # hacky
            f.model = model_or_instance
            f.instance = f.model()

        else:
            f.instance = model_or_instance
            f.model = f.instance.__class__

        if hasattr(f.instance, 'menu_actions'):
            f.menu_actions = f.instance.menu_actions

        if hasattr(f.instance, 'menu_related'):
            f.menu_related = f.instance.menu_related

        return f
    
    
    def __init__(self, model_or_instance, mode=None, prefix=None, name=None, title=None, method=None, action=None):
        super(BoundForm, self).__init__(prefix=prefix, name=name, title=title, method=method, action=action)
        self.mode = mode


class AddForm(BoundForm):

    preview = None

    def __new__(cls, model_or_instance, mode='add', prefix=None, name=None, title=None, method=None, action=None):
        f = super(AddForm, cls).__new__(cls, model_or_instance, prefix=prefix, name=name, title=title, method=method, action=action)

        for field in f.model._meta.sorted_fields:

            if  (not f.fields.has_key(field.name)    and # means this field was already defined in the class definition for this form
                not field.form_widget is None       and # means this field should by ignored
                not (hasattr(cls, field.name) and isinstance(getattr(cls, field.name), poobrains.form.fields.Field))): # second clause is to avoid problems with name collisions (for instance on "name")

                    setattr(f, field.name, field.form())

        f.controls['reset'] = poobrains.form.Button('reset', label='Reset')
        f.controls['preview'] = poobrains.form.Button('submit', name='preview', value='preview', label='Preview')
        f.controls['submit'] = poobrains.form.Button('submit', name='submit', value='submit', label='Save')

        return f


    def __init__(self, model_or_instance, mode='add', prefix=None, name=None, title=None, method=None, action=None):
        
        if not name:
            name = '%s-%s' % (self.model.__name__, self.instance.handle_string.replace('.', '-'))
    
        super(AddForm, self).__init__(model_or_instance, mode=mode, prefix=prefix, name=name, title=title, method=method, action=action)

        if not title:
    
            if hasattr(self.instance, 'title') and self.instance.title:
                self.title = "%s %s '%s'" % (self.mode, self.model.__name__, self.instance.title)
            elif self.instance.name:
                self.title = "%s %s '%s'" % (self.mode, self.model.__name__, self.instance.name)
            elif self.instance.id:
                self.title = "%s %s #%d" % (self.mode, self.model.__name__, self.instance.id)
            else:
                try:

                    if self.instance._pk:
                        self.title = "%s %s '%s'" % (self.mode, self.model.__name__, self.instance._pk)
                    else:
                        self.title = "%s %s" % (self.mode, self.model.__name__)

                except Exception as e:
                    self.title = "%s %s" % (self.mode, self.model.__name__)

        for name, field in self.fields.iteritems():
            if hasattr(self.instance, name):
                try:
                    field.value = getattr(self.instance, name)
                except Exception as e:
                    pass
 

    def process(self, submit, exceptions=False):

        if not self.readonly:
            
            for field in self.model._meta.sorted_fields:
                if not field.form_widget is None: # check if the field should be ignored by the form
                    #if self.fields[field.name].value is not None: # see https://github.com/coleifer/peewee/issues/107
                    if not self.fields[field.name].empty:
                        setattr(self.instance, field.name, self.fields[field.name].value)
                    elif field.default is not None:
                        setattr(self.instance, field.name, field.default() if callable(field.default) else field.default)
                    elif field.null:
                        setattr(self.instance, field.name, None)


            if submit == 'submit':

                try:

                    if self.mode == 'add':
                        saved = self.instance.save(force_insert=True) # To make sure Administerables with CompositeKey as primary get inserted properly
                    else:
                        saved = self.instance.save()

                    if saved:
                        flash(u"Saved %s %s." % (self.model.__name__, self.instance.handle_string))

                        for fieldset in self.fieldsets:

                            try:
                                fieldset.process(submit, self.instance)

                            except Exception as e:

                                if exceptions:
                                    raise

                                flash(u"Failed to process fieldset '%s.%s'." % (fieldset.prefix, fieldset.name), 'error')
                                app.logger.error(u"Failed to process fieldset %s.%s - %s: %s" % (fieldset.prefix, fieldset.name, type(e).__name__, e.message.decode('utf-8')))

                        try:
                            return redirect(self.instance.url('edit'))
                        except LookupError:
                            return self
                    else:

                        flash(u"Couldn't save %s." % self.model.__name__)

                except poobrains.errors.ValidationError as e:

                    flash(e.message, 'error')

                    if e.field:
                        self.fields[e.field].errors.append(e)

                except peewee.IntegrityError as e:

                    if exceptions:
                        raise

                    flash(u'Integrity error: %s' % e.message.decode('utf-8'), 'error')
                    app.logger.error(u"Integrity error: %s" % e.message.decode('utf-8'))

                except Exception as e:
                    if exceptions:
                        raise

                    flash(u"Couldn't save %s for mysterious reasons." % self.model.__name__)
                    app.logger.error(u"Couldn't save %s. %s: %s" % (self.model.__name__, type(e).__name__, e.message.decode('utf-8')))


            elif submit == 'preview':
                self.preview = self.instance.render('full')

        else:
            flash(u"Not handling readonly form '%s'." % self.name)

        return self

poobrains.form.AddForm = AddForm


class EditForm(AddForm):
    
    def __new__(cls, model_or_instance, mode='edit', prefix=None, name=None, title=None, method=None, action=None):
        f = super(EditForm, cls).__new__(cls, model_or_instance, mode=mode, prefix=prefix, name=name, title=title, method=method, action=action)
        for pkfield in f.model._meta.get_primary_keys():
            if f.fields.has_key(pkfield.name):
                f.fields[pkfield.name].readonly = True # Make any primary key fields read-only

        return f

   

    def __init__(self, model_or_instance, mode='edit', prefix=None, name=None, title=None, method=None, action=None):
        super(EditForm, self).__init__(model_or_instance, mode=mode, prefix=prefix, name=name, title=title, method=method, action=action)

poobrains.form.EditForm = EditForm


class DeleteForm(BoundForm):

    def __new__(cls, model_or_instance, mode='delete', prefix=None, name=None, title=None, method=None, action=None):
        
        f = super(DeleteForm, cls).__new__(cls, model_or_instance, prefix=prefix, name=None, title=title, method=method, action=action)

        f.title = "Delete %s" % f.instance.name
        f.warning = poobrains.form.fields.Message('deletion_irrevocable', value='Deletion is not revocable. Proceed?')
        f.submit = poobrains.form.Button('submit', name='submit', value='delete', label=u'☠')

        return f


    def __init__(self, model_or_instance, mode='delete', prefix=None, name=None, title=None, method=None, action=None):
        super(DeleteForm, self).__init__(model_or_instance, mode=mode, prefix=prefix, name=self.name, title=title, method=method, action=action)
        if not title:
            if hasattr(self.instance, 'title') and self.instance.title:
                self.title = "Delete %s %s" % (self.model.__name__, self.instance.title)
            else:
                self.title = "Delete %s %s" % (self.model.__name__, unicode(self.instance._pk))

    
    def process(self, submit):

        if hasattr(self.instance, 'title') and self.instance.title:
            message = "Deleted %s '%s'." % (self.model.__name__, self.instance.title)
        else:
            message = "Deleted %s '%s'." % (self.model.__name__, unicode(self.instance._pk))
        self.instance.delete_instance(recursive=True)
        flash(message)

        return redirect(self.model.url('teaser')) # TODO app.admin.get_listing_url?

poobrains.form.DeleteForm = DeleteForm


class AccessField(poobrains.form.fields.Field):

    read = None
    update = None
    delete = None

    def __init__(self, **kwargs):

        super(AccessField, self).__init__(**kwargs)
        self.read = poobrains.form.fields.Checkbox(name='read', label='Read', help_text='teaser, full view and the like')
        self.update = poobrains.form.fields.Checkbox(name='update', label='Update', help_text='mostly edit mode')
        self.delete = poobrains.form.fields.Checkbox(name='delete', label='Delete')


    def __getattribute__(self, name):

        if name == 'value':
            return self.value_string

        return super(AccessField, self).__getattribute__(name)


    def __setattr__(self, name, value):

        if name == 'prefix':
            for field in [self.read, self.update, self.delete]:
                field.prefix = '%s.%s' % (value, self.name)

        elif name == 'value':

            if 'r' in value:
                self.read.value = True

            if 'u' in value:
                self.update.value = True

            if 'd' in value:
                self.delete.value = True

        super(AccessField, self).__setattr__(name, value)


    def bind(self, value):

        if value == '':

            self.read.value = False
            self.update.value = False
            self.delete.value = False

        else:

            self.read.value = value.get('read', False)
            self.update.value = value.get('update', False)
            self.delete.value = value.get('delete', False)


    @property
    def value_string(self):

        s = ''
        if self.read.value:
            s += 'r'

        if self.update.value:
            s += 'u'

        if self.delete.value:
            s += 'd'

        return s


class Permission(poobrains.helpers.ChildAware):
   
    instance = None
    op = None
    label = None
    choices = [
        ('grant', 'Grant'),
        ('deny', 'Explicitly deny')
    ]

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
        # group_deny = GroupPermission.select().join(Group).join(UserGroup).join(User).where(UserGroup.user == user, GroupPermission.permission == cls.__name__, GroupPermission.access == 'deny').count()
        group_deny = False
        for group in user.groups:
            if group.own_permissions.has_key(cls.__name__) and group.own_permissions[cls.__name__] == 'deny':
                group_deny = True
                break

        if group_deny:
            raise AccessDenied("YOU SHALL NOT PASS!")

        #group_grant = GroupPermission.select().join(Group).join(UserGroup).join(User).where(UserGroup.user == user, GroupPermission.permission == cls.__name__, GroupPermission.access == 'grant').count()
        group_grant = False
        for group in user.groups:
            if group.own_permissions.has_key(cls.__name__) and group.own_permissions[cls.__name__] == 'grant':
                group_grant = True
                break

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


class PermissionParamType(poobrains.form.types.StringParamType):

    def convert(self, value, param, ctx):

        cleaned_string = super(PermissionParamType, self).convert(value, param, ctx)

        try:
            permission, access = cleaned_string.split('.')
        except Exception as e:
            self.fail('Could not split value to permission and access: %s' % cleaned_string)

        return (permission, access)

PERMISSION = PermissionParamType()
poobrains.form.types.PermissionParamType = PermissionParamType
poobrains.form.types.PERMISSION = PERMISSION


class FormPermissionField(poobrains.form.fields.Select):

    default = (None, None)
    type = PERMISSION

    def __init__(self, *args, **kwargs):
        super(FormPermissionField, self).__init__(*args, **kwargs)

        self.choices = []

        permissions = Permission.class_children_keyed()
        for perm_name in sorted(permissions):
            perm = permissions[perm_name]
            self.choices.append(([('%s.%s' % (perm_name, value), label) for (value, label) in perm.choices], perm_name))


    def validate(self):
        permission, access = self.value

        if not permission in Permission.class_children_keyed().keys():
            raise poobrains.errors.ValidationError('Unknown permission: %s' % permission)

        perm_class = Permission.class_children_keyed()[permission]
        choice_values = [t[0] for t in perm_class.choices]
        if not access in choice_values:
            raise poobrains.errors.ValidationError("Unknown access mode '%s' for permission '%s'." % (access, permission))


def admin_listing_actions(cls):

    m = poobrains.rendering.Menu('actions')
    if cls._meta.modes.has_key('add'):
        m.append(cls.url('add'), 'add new %s' % (cls.__name__,))

    return m


@app.admin.box('menu_main')
def admin_menu():

    try:
        AccessAdminArea.check(g.user) # check if current user may even access the admin area

        menu = poobrains.rendering.Menu('main')
        menu.title = 'Administration'

        for administerable, listings in app.admin.listings.iteritems():

            for mode, endpoints in listings.iteritems():

                for endpoint in endpoints: # iterates through endpoints.keys()
                    menu.append(url_for('admin.%s' % endpoint), administerable.__name__)

        return menu

    except AccessDenied:
        return None


@app.admin.route('/')
@poobrains.helpers.themed
def admin_index():

    try:

        AccessAdminArea.check(g.user)

        container = poobrains.rendering.Container(title='Administration', mode='full')
        
        for administerable, listings in app.admin.listings.iteritems():

            subcontainer = poobrains.rendering.Container(css_class='administerable-actions', mode='full')
            menu = poobrains.rendering.Menu('listings-%s' % administerable.__name__)
            for mode, endpoints in listings.iteritems():

                for endpoint in endpoints: # iterates through endpoints.keys()
                    menu.append(url_for('admin.%s' % endpoint), administerable.__name__)

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

            return func(*args, **kwargs)

        return substitute

    return decorator


def protected(func):

    @functools.wraps(func)
    def substitute(cls_or_instance, mode=None, *args, **kwargs):

        if not mode:
            raise Exception('Need explicit mode in @protected.')

        user = g.user # FIXME: How do I get rid of the smell?
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


@app.expose('/cert/', force_secure=True)
class ClientCertForm(poobrains.form.Form):

    #passphrase = poobrains.form.fields.ObfuscatedText()
    title = "Be safe, certificatisize yourself!"
    token = poobrains.form.fields.ObfuscatedText(label='Token')
    key = poobrains.form.fields.Keygen()
    not_after = poobrains.form.fields.Date(label='Expiry on', required=True, help_text="The date this certificate expires on. Expired certificates can not be used to log in.", default=lambda: datetime.date.today() + datetime.timedelta(seconds=app.config['CERT_MAX_LIFETIME']))
    keygen_submit = poobrains.form.Button('submit', label='Client-side: Keygen')
    pgp_submit = poobrains.form.Button('submit', label="Server-side: PGP-mail")
    tls_submit = poobrains.form.Button('submit', label="Server-side: HTTPS")

    def __init__(self, *args, **kwargs):

        super(ClientCertForm, self).__init__(*args, **kwargs)
        if request.method == 'GET':
            session['key_challenge'] = self.fields['key'].challenge


    def process(self, submit):

        time.sleep(random.random() * 0.1) # should make timing side channel attacks harder

        try:
            # creation time older than this means token is dead.
            deathwall = datetime.datetime.now() - datetime.timedelta(seconds=app.config['TOKEN_VALIDITY'])

            token = ClientCertToken.get(
                ClientCertToken.token == self.fields['token'].value,
                ClientCertToken.created > deathwall,
                ClientCertToken.redeemed == False
            )

        except peewee.DoesNotExist as e:
            
            flash(u"No such token.", 'error')
            return redirect(self.url())
            
        cert_info = ClientCert()
        cert_info.user = token.user
        cert_info.name = token.cert_name

        not_after = datetime.datetime(year=self.fields['not_after'].value.year, month=self.fields['not_after'].value.month, day=self.fields['not_after'].value.day)
        
        if self.controls['keygen_submit'].value:

            try:
                client_cert = token.user.gen_clientcert_from_spkac(token.cert_name, self.fields['key'].value, session['key_challenge'], not_after)
                del session['key_challenge']

            except pyspkac.spkac.SPKAC_Decode_Error as e:

                app.logger.error(e.message)
                return poobrains.rendering.RenderString("Client certificate creation failed. Pwease no cwacky!")

            cert_info.keylength = client_cert.get_pubkey().size() * 8 # .size gives length in byte
            cert_info.fingerprint = client_cert.get_fingerprint('sha512')

            not_before = client_cert.get_not_before().get_datetime() # contains tzinfo, which confuses peewee ( https://github.com/coleifer/peewee/issues/914)
            cert_info.not_before = datetime.datetime(not_before.year, not_before.month, not_before.day, not_before.hour, not_before.minute, not_before.second)

            not_after = client_cert.get_not_after().get_datetime() # contains tzinfo, which confuses peewee ( https://github.com/coleifer/peewee/issues/914)
            cert_info.not_after = datetime.datetime(not_after.year, not_after.month, not_after.day, not_after.hour, not_after.minute, not_after.second)

            r = werkzeug.wrappers.Response(client_cert.as_pem())
            r.mimetype = 'application/x-x509-user-cert'

        #elif submit in ('ClientCertForm.pgp_submit', 'ClientCertForm.tls_submit'):
        elif self.controls['pgp_submit'].value or self.controls['tls_submit'].value:

            passphrase = poobrains.helpers.random_string_light()

            try:

                pkcs12 = token.user.gen_keypair_and_clientcert(token.cert_name, not_after)


            except Exception as e:
                return poobrains.rendering.RenderString("Client certificate creation failed.")

            cert_info.keylength = pkcs12.get_certificate().get_pubkey().bits() 
            cert_info.fingerprint = pkcs12.get_certificate().digest('sha512').replace(':', '')
            cert_info.not_before = datetime.datetime.strptime(pkcs12.get_certificate().get_notBefore(), '%Y%m%d%H%M%SZ')
            cert_info.not_after = datetime.datetime.strptime(pkcs12.get_certificate().get_notAfter(), '%Y%m%d%H%M%SZ')

            #if submit == 'ClientCertForm.tls_submit':
            if self.controls['tls_submit'].value:
                r = werkzeug.wrappers.Response(pkcs12.export(passphrase=passphrase))
                r.mimetype = 'application/pkcs-12'
                flash(u"The passphrase for this delicious bundle of crypto is '%s'" % passphrase)

            else: # means pgp

                text = "Hello %s. Here's your new set of keys to the gates of Shambala.\nYour passphrase is '%s'." % (token.user.name, passphrase)

                mail = poobrains.mailing.Mail(token.user.pgp_fingerprint)
                mail['Subject'] = 'Bow before entropy'
                mail['To'] = token.user.mail

                mail.attach(poobrains.mailing.MIMEText(text))
                pkcs12_attachment = poobrains.mailing.MIMEApplication(pkcs12.export(passphrase=passphrase), _subtype='pkcs12')
                mail.attach(pkcs12_attachment)

                mail.send()

                flash(u"Your private key and client certificate have been send to '%s'." % token.user.mail)

                r = self


        try:
            cert_info.save()

        except Exception as e:

            if app.debug:
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
                app.logger.warning("Unknown access mode '%s' for User %d with Permission %s" % (access, user.id, cls.__name__))
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

        op_abbr = op[0]

        if user.own_permissions.has_key(cls.__name__):

            access = user.own_permissions[cls.__name__]
            if access == 'deny':
                raise AccessDenied("YOU SHALL NOT PASS!")

            elif access == 'own_instance':
                return q.where(protected.owner == user, protected.access.contains(op_abbr))

            elif access == 'instance':
                return q.where(protected.access.contains(op_abbr))

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
                return q.where(protected.group.in_(allowed_groups), protected.access.contains(op_abbr))

            elif 'instance' in group_access.keys():
                return q.where(protected.access.contains(op_abbr))

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
    offset = None
    pagination = None

    def __new__(cls, related_model, related_field, instance, offset=0, prefix=None, name=None, title=None, method=None, action=None):

        endpoint = request.endpoint
        if not endpoint.endswith('_offset'):
            endpoint = '%s_offset' % (endpoint,)

        f = super(RelatedForm, cls).__new__(cls, prefix=prefix, name=name, title=title, method=method, action=action)
        
        f.pagination = poobrains.storage.Pagination(
            [related_model.list('read', g.user).where(related_field == instance)],
            offset,
            endpoint,
            handle=instance.handle_string # needed for proper URL building
        )

        for related_instance in f.pagination.results:
            try:

                key = related_instance.handle_string.replace('.', '-')

                # Fieldset to edit an existing related instance of this instance
                setattr(f, key, related_instance.fieldset('edit'))

                if f.fields[key].fields.has_key(related_field.name):
                    setattr(f.fields[key], related_field.name, poobrains.form.fields.Value(value=instance._pk))

            except AccessDenied as e:
                pass

        f.controls['reset'] = poobrains.form.Button('reset', label='Reset')
        f.controls['submit'] = poobrains.form.Button('submit', name='submit', value='submit', label='Save')

        return f

    
    def __init__(self, related_model, related_field, instance, offset=0, prefix=None, name=None, title=None, method=None, action=None):

        super(RelatedForm, self).__init__(prefix=None, name=None, title=None, method=None, action=None)

        self.instance = instance
        self.related_model = related_model
        self.related_field = related_field

        self.title = "%s for %s %s" % (self.related_model.__name__, self.instance.__class__.__name__, self.instance.handle_string)

   
    def process(self, submit):

        if not self.readonly:
            for fieldset in self.fieldsets:
                try:
                    fieldset.process(submit, self.instance)
                except Exception as e:
                    flash(u"Failed to process fieldset '%s.%s'." % (fieldset.prefix, fieldset.name))
                    app.logger.error("Failed to process fieldset %s.%s - %s: %s" % (fieldset.prefix, fieldset.name, type(e).__name__, e.message))
                        
            return redirect(request.url)
        return self


class UserPermissionAddForm(AddForm):

    
    def __new__(cls, model_or_instance, mode='add', prefix=None, name=None, title=None, method=None, action=None):

        f = super(UserPermissionAddForm, cls).__new__(cls, model_or_instance, prefix=prefix, name=name, title=title, method=method, action=action)
        del(f.fields['access'])
        del(f.fields['permission'])
        f.permission = FormPermissionField()

        return f


    def process(self, submit):
        op = self.instance._meta.modes[self.mode]

        self.instance.user = self.fields['user'].value
        self.instance.permission = self.fields['permission'].value[0]
        self.instance.access = self.fields['permission'].value[1]
        if op == 'create':
            self.instance.save(force_insert=True)
            return redirect(self.instance.url('edit'))
        else:
            self.instance.save()
        return self


class GroupPermissionAddForm(AddForm):

    
    def __new__(cls, model_or_instance, mode='add', prefix=None, name=None, title=None, method=None, action=None):

        f = super(GroupPermissionAddForm, cls).__new__(cls, model_or_instance, prefix=prefix, name=name, title=title, method=method, action=action)
        del(f.fields['access'])
        del(f.fields['permission'])
        f.permission = FormPermissionField()

        return f


    def process(self, submit):

        op = self.instance._meta.modes[self.mode]

        self.instance.group = self.fields['group'].value
        self.instance.permission = self.fields['permission'].value[0]
        self.instance.access = self.fields['permission'].value[1]
        if op == 'create':
            self.instance.save(force_insert=True)
            return redirect(self.instance.url('edit'))
        else:
            self.instance.save()
        return self


class GroupPermissionEditForm(EditForm):

    def __new__(cls, model_or_instance, *args, **kwargs):

        f = super(GroupPermissionEditForm, cls).__new__(cls, model_or_instance, *args, **kwargs)
        f.fields['permission'].choices = f.instance.permission_class.choices

        return f


class BaseAdministerable(PermissionInjection, poobrains.storage.ModelBase):

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


    def render(self, mode='full'):

        op = self._meta.modes[mode]

        try:
            self.permissions[op].check(g.user)

        except AccessDenied:

            if mode == 'inline':
                return Markup(poobrains.rendering.RenderString("Access Denied for %s." % self.__class__.__name__))

            raise

        return super(Protected, self).render(mode)


#class ProtectedForm(Protected, poobrains.form.Form):
#    pass # let's just hope this works out of the box


class Administerable(poobrains.storage.Storable, Protected):
    
    __metaclass__ = BaseAdministerable

    form_add = AddForm # TODO: move form_ into class Meta?
    form_edit = EditForm
    form_delete = DeleteForm

    related_form = RelatedForm # TODO: make naming consistent

    class Meta:
        abstract = True
        related_use_form = False # Whether we want to use Administerable.related_form in related view for administration.
        permission_class = Permission

        modes = collections.OrderedDict([
            ('add', 'create'),
            ('teaser', 'read'),
            ('inline', 'read'),
            ('full', 'read'),
            ('edit', 'update'),
            ('delete', 'delete')
        ])


    @property
    def menu_actions(self):

        try:
            if self._pk is None:
                return None

        except peewee.DoesNotExist: # matches both cls.DoesNotExist and ForeignKey related models DoesNotExist. Should only happen when primary key is a multi-column key containing a foreign key
            return None

        user = g.user
        actions = poobrains.rendering.Menu('actions')

        for mode in self.__class__._meta.modes:

            try:
                op = self._meta.modes[mode]

                if op != 'create':
                    self.permissions[op].check(user)
                    actions.append(self.url(mode), mode)

            except AccessDenied:
                app.logger.debug("Not generating %s link for %s %s because this user is not authorized for it." % (mode, self.__class__.__name__, self.handle_string))
            except LookupError:
                pass
                #app.logger.debug("Couldn't create %s link for %s" % (mode, self.handle_string))

        return actions


    @property
    def menu_related(self):

        try:
            self._pk
        except peewee.DoesNotExist:
            return None

        user = g.user
        menu = poobrains.rendering.Menu('related')

        for related_field, related_model in self._meta.backrefs.iteritems(): # Add Models that are associated by ForeignKeyField, like /user/foo/userpermissions

            if related_model is not self.__class__ and issubclass(related_model, Administerable) and not related_model._meta.abstract:
                try:
                    menu.append(self.related_url(related_field) , related_model.__name__)
                except LookupError:
                    pass
        return menu


    def related_url(self, related_field, add=False):
        return app.get_related_view_url(self.__class__, self.handle_string, related_field, add=add)


    @classmethod
    def class_form(cls, mode=None):

        instance = cls()
        return instance.form(mode)


    def form(self, mode=None):
        
        n = 'form_%s' % mode
        if not hasattr(self, n):
            raise NotImplementedError("Form class %s.%s missing." % (self.__class__.__name__, n))

        form_class = getattr(self, n)
        return form_class(mode=mode)#, name=None, title=None, method=None, action=None)


    def fieldset(self, mode=None):

        return poobrains.form.ProxyFieldset(self.form(mode))


    @classmethod
    def class_view(cls, mode=None, handle=None, **kwargs):
        
        op = cls._meta.modes[mode]
       
        if op == 'create':
            instance = cls()
        else:
            try:
                instance = cls.load(handle)
            except ValueError as e:
                raise cls.DoesNotExist("This isn't even the right type!")

        return instance.view(mode=mode, handle=handle, **kwargs)


    @protected
    @poobrains.helpers.themed
    def view(self, mode='teaser', handle=None, **kwargs):

        """
        view function to be called in a request context
        """
        
        if self._meta.modes[mode] in ['create', 'update', 'delete']:

            f = self.form(mode)
            return poobrains.helpers.ThemedPassthrough(f.view('full'))

        return self


    @classmethod
    def list(cls, op, user, handles=None, ordered=True, fields=[]):
        q = super(Administerable, cls).list(op, user, handles=handles, ordered=ordered, fields=fields)
        return cls.permissions[op].list(cls, q, op, user)


    @classmethod
    def related_view(cls, related_field=None, handle=None, offset=0):

        if related_field is None:
            raise TypeError("%s.related_view needs Field instance for parameter 'related_field'. Got %s (%s) instead." % (cls.__name__, type(field).__name__, unicode(field)))

        related_model = related_field.model
        instance = cls.load(handle)

        actions = poobrains.rendering.Menu('related-add')
        actions.append(instance.related_url(related_field, add=True), 'Add new')

        if request.blueprint == 'admin' and related_model._meta.related_use_form:
            if hasattr(related_model, 'related_form'):
                form_class = related_model.related_form
            else:
                form_class = functools.partial(RelatedForm, related_model) # TODO: does this even work? and more importantly, is it even needed?

            f = form_class(related_field, instance, offset=offset)
            f.pre = actions
            f.menu_actions = instance.menu_actions
            f.menu_related = instance.menu_related
            
            return f.view('full')

        else:
            return poobrains.storage.Listing(
                cls=related_model,
                query=related_model.list('read', g.user).where(related_field == instance),
                offset=offset,
                menu_actions=instance.menu_actions,
                menu_related=instance.menu_related,
                pre=actions,
                pagination_options={'handle': handle}
            ).view()


    @classmethod
    def related_view_add(cls, related_field=None, handle=None):
        
        related_model = related_field.model
        instance = cls.load(handle)

        f = related_model.class_form('add')
        f.menu_actions = instance.menu_actions
        f.menu_related = instance.menu_related

        if f.fields.has_key(related_field.name):
            f.fields[related_field.name].value = instance

        return f.view()


class Named(Administerable, poobrains.storage.Named):

    class Meta:
        abstract = True
        handle_fields = ['name']


class User(Named):

    mail = poobrains.storage.fields.CharField(null=True) # FIXME: implement an EmailField
    pgp_fingerprint = poobrains.storage.fields.CharField(null=True)
    mail_notifications = poobrains.storage.fields.BooleanField(default=False)
    about = poobrains.md.MarkdownField(null=True)

    offset = None
    profile_posts = None
    profile_pagination = None

    _on_profile = []


    def __init__(self, *args, **kwargs):

        super(User, self).__init__(*args, **kwargs)
        self.offset = 0
        self.profile_posts = []

    @locked_cached_property
    def own_permissions(self):

        permissions = collections.OrderedDict()
        for up in self._permissions:
            permissions[up.permission] = up.access

        return permissions

    @locked_cached_property
    def groups(self):

        groups = []
        for ug in self._groups:
            groups.append(ug.group)

        return groups

    
    def gen_clientcert_from_spkac(self, name, spkac, challenge, not_after):

        invalid_after = datetime.datetime.now() + datetime.timedelta(seconds=app.config['CERT_MAX_LIFETIME']) 
        if not_after > invalid_after:
            raise poobrains.errors.ExposedError("not_after too far into the future, max allowed %s but got %s" % (invalid_after, not_after))

        try:

            ca_key = M2Crypto.EVP.load_key(app.config['CA_KEY'])
            ca_cert = M2Crypto.X509.load_cert(app.config['CA_CERT'])

        except Exception as e:

            app.logger.error("Client certificate could not be generated. Invalid CA_KEY or CA_CERT.")
            app.logger.debug(e)
            flash(u"Plumbing issue. Invalid CA_KEY or CA_CERT.")
            raise e

        common_name = '%s:%s@%s' % (self.name, name, app.config['SITE_NAME'])
        spkac = pyspkac.SPKAC(spkac, challenge, CN=common_name) # TODO: Make sure CN is unique
        spkac.push_extension(M2Crypto.X509.new_extension('keyUsage', 'digitalSignature, keyEncipherment, keyAgreement', critical=True))
        spkac.push_extension(M2Crypto.X509.new_extension('extendedKeyUsage', 'clientAuth, emailProtection, nsSGC'))

        #spkac.subject.C = ca_cert.get_subject().C

        not_before = int(time.time())
        not_after = int(time.mktime(not_after.timetuple()))

        serial = int(time.time())

        return spkac.gen_crt(ca_key, ca_cert, serial, not_before, not_after, hash_algo='sha512')


    def gen_keypair_and_clientcert(self, name, not_after):

        invalid_after = datetime.datetime.now() + datetime.timedelta(seconds=app.config['CERT_MAX_LIFETIME']) # FIXME: DRY!
        if not_after > invalid_after:
            raise poobrains.errors.ExposedError("not_after too far into the future, max allowed %s but got %s" % (invalid_after, not_after))

        common_name = '%s:%s@%s' % (self.name, name, app.config['SITE_NAME'])

        fd = open(app.config['CA_KEY'], 'rb')
        ca_key = openssl.crypto.load_privatekey(openssl.crypto.FILETYPE_PEM, fd.read())
        fd.close()
        del fd

        fd = open(app.config['CA_CERT'], 'rb')
        ca_cert = openssl.crypto.load_certificate(openssl.crypto.FILETYPE_PEM, fd.read())
        fd.close()
        del fd

        keypair = openssl.crypto.PKey()
        keypair.generate_key(openssl.crypto.TYPE_RSA, app.config['CRYPTO_KEYLENGTH'])

        extensions = []
        extensions.append(openssl.crypto.X509Extension('keyUsage', True, 'digitalSignature, keyEncipherment, keyAgreement'))
        extensions.append(openssl.crypto.X509Extension('extendedKeyUsage', True, 'clientAuth'))

        cert = openssl.crypto.X509()
        cert.set_version(2) # 2 == 3, WHAT THE FUCK IS WRONG WITH THESE PEOPLE!?
        cert.add_extensions(extensions)
        cert.set_issuer(ca_cert.get_subject())
        cert.set_pubkey(keypair)
        cert.gmtime_adj_notBefore(0)
        cert.set_notAfter(not_after.strftime('%Y%m%d%H%M%SZ'))
        cert.set_serial_number(int(time.time())) # FIXME: This is bad, but probably won't fuck us over for a while ¯\_(ツ)_/¯
        cert.get_subject().CN = common_name

        cert.sign(ca_key, 'sha512')

        pkcs12 = openssl.crypto.PKCS12()
        pkcs12.set_ca_certificates([ca_cert])
        pkcs12.set_privatekey(keypair)
        pkcs12.set_certificate(cert)
        pkcs12.set_friendlyname(str(name))

        return pkcs12


    def mkmail(self):

        # FIXME: shitty name, not a pattern used anywhere else in poobrains
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


    @classmethod
    def on_profile(cls, model):

        """
        decorator. allows adding subclasses of Owned to the content-listing on profile pages (~/<username>).

        NOTE: the passed model needs to have a datetime field with the name 'date'. This is needed for ordering.
        """
        assert issubclass(model, Owned) and hasattr(model, 'date'), "Only Owned subclasses with a 'date' field can be @User.profile'd. %s does not qualify." % model.__name__

        cls._on_profile.append(model) 

        return model


    @property
    def models_on_profile(self):

        models = []

        for model in self._on_profile:
            if model._meta.abstract:
                for submodel in model.class_children():
                    models.append(submodel)
            else:
                models.append(model)

        return models


    def view(self, mode='teaser', handle=None, offset=0, **kwargs):

        self.offset = offset

        if len(self.models_on_profile):

            queries = []

            for model in self.models_on_profile:

                try:
                    queries.append(model.list('read', g.user, ordered=False, fields=[peewee.SQL("'%s'" % model.__name__).alias('model'), model.id, model.date.alias('date'), model.title]))
                except AccessDenied:
                    pass # ignore models we aren't allowed to read

            # construct the final UNION ALL query, This can be shortened to sum(queries) if https://github.com/coleifer/peewee/issues/1545 gets fixed

            if len(queries):
                q = queries[0]
                for query in queries[1:]:
                    q += query

                q = q.order_by(model.date.alias('date').desc())
                self.profile_pagination = poobrains.storage.Pagination([q], offset=offset, limit=app.config['PAGINATION_COUNT'], endpoint='site.user_profile_offset', handle=self.handle_string)
                q = q.offset(offset).limit(app.config['PAGINATION_COUNT']) # model.date.desc() fails if this model hasn't yielded any results, hence alias is needed

                info_sorted = [] # tuples of (model_name, id) in the same order as in the sql result
                info_by_model = {} # dict with lists of ids keyed by model name

                for row in q.iterator():

                    info_sorted.append((row.model, row.id))

                    if not info_by_model.has_key(row.model):
                        info_by_model[row.model] = []
                        
                    info_by_model[row.model].append(row.id)

                posts_by_model = {}

                for model_name, ids in info_by_model.iteritems():
                
                    model = Owned.class_children_keyed()[model_name]
                    posts_by_model[model_name] = {}
                    for instance in model.select().where(model.id << ids):
                        posts_by_model[model_name][instance.id] = instance

                for (model_name, id) in info_sorted:
                    self.profile_posts.append(posts_by_model[model_name][id])

        return super(User, self).view(mode=mode, handle=handle, **kwargs)

app.site.add_view(User, '/~<handle>/', mode='full', endpoint='user_profile')
app.site.add_view(User, '/~<handle>/+<int:offset>/', mode='full', endpoint='user_profile_offset')


class UserPermission(Administerable):

    form_add = UserPermissionAddForm

    class Meta:
        primary_key = peewee.CompositeKey('user', 'permission')
        order_by = ('user', 'permission')
        related_use_form = True

    user = poobrains.storage.fields.ForeignKeyField(User, related_name='_permissions')
    permission = poobrains.storage.fields.CharField(max_length=50)
    access = poobrains.storage.fields.CharField(null=False, form_widget=poobrains.form.fields.Select)

    
    @property
    def permission_class(self):
        
        try:
            return Permission.class_children_keyed()[self.permission]

        except KeyError:
            app.logger.error("Unknown permission '%s' associated to user #%d." % (self.permission, self.user_id)) # can't use self.user.name because dat recursion
            #TODO: Do we want to do more, like define a permission_class that always denies access?


    def save(self, *args, **kwargs):

        valid_permission_names = []
        for cls in Permission.class_children():
            valid_permission_names.append(cls.__name__)

        if self.permission not in valid_permission_names:
            raise ValueError("Invalid permission name: %s" % self.permission)

        return super(UserPermission, self).save(*args, **kwargs)

    
    def form(self, mode=None):

        op = self._meta.modes[mode]
        f = super(UserPermission, self).form(mode=mode)

        if op == 'update':
            f.fields['access'].choices = self.permission_class.choices 

        return f


class Group(Named):

    # TODO: Almost identical to User. DRY.


    @locked_cached_property
    def own_permissions(self):

        own_permissions = collections.OrderedDict()
        for gp in self._permissions:
            own_permissions[gp.permission] = gp.access

        return own_permissions

    
class UserGroup(Administerable):

    class Meta:
        primary_key = peewee.CompositeKey('user', 'group')
        order_by = ('user', 'group')

    user = poobrains.storage.fields.ForeignKeyField(User, related_name='_groups')
    group = poobrains.storage.fields.ForeignKeyField(Group, related_name='_users')


class GroupPermission(Administerable):

    form_add = GroupPermissionAddForm
    form_edit = GroupPermissionEditForm

    class Meta:
        primary_key = peewee.CompositeKey('group', 'permission')
        order_by = ('group', 'permission')

    group = poobrains.storage.fields.ForeignKeyField(Group, null=False, related_name='_permissions')
    permission = poobrains.storage.fields.CharField(max_length=50)
    access = poobrains.storage.fields.CharField(null=False, form_widget=poobrains.form.fields.Select)

    
    @property
    def permission_class(self):

        try:
            return Permission.class_children_keyed()[self.permission]

        except KeyError:
            app.logger.error("Unknown permission '%s' associated to user #%d." % (self.permission, self.group_id)) # can't use self.group.name because dat recursion
            #TODO: Do we want to do more, like define a permission_class that always denies access?


    def form(self, mode=None):

        op = self._meta.modes[mode]
        f = super(GroupPermission, self).form(mode=mode)

        if op == 'update':
            f.fields['access'].choices = self.permission_class.choices 

        return f


    @property
    def title(self):
        return "%s-%s" % (self.group.name, self.permission)


class ClientCertToken(Administerable, Protected):

    validity = None
    user = poobrains.storage.fields.ForeignKeyField(User, related_name='clientcerttokens')
    created = poobrains.storage.fields.DateTimeField(default=datetime.datetime.now, null=False)
    cert_name = poobrains.storage.fields.CharField(null=False, max_length=32, constraints=[poobrains.storage.RegexpConstraint('cert_name', '^[a-zA-Z0-9_\- ]+$')])
    token = poobrains.storage.fields.CharField(unique=True, default=poobrains.helpers.random_string_light, form_widget=None)
    # passphrase = poobrains.storage.fields.CharField(null=True) # TODO: Find out whether we can pkcs#12 encrypt client certs with a passphrase and make browsers still eat it.
    redeemed = poobrains.storage.fields.BooleanField(default=False, null=False)


    def __init__(self, *args, **kw):

        self.validity = app.config['TOKEN_VALIDITY']
        super(ClientCertToken, self).__init__(*args, **kw)

    @property
    def redeemable(self):
        return (not self.redeemed) and ((self.created + datetime.timedelta(seconds=self.validity)) < datetime.datetime.now())

    def save(self, force_insert=False, only=None):

        if not self.id or force_insert:

            user_token_count = self.__class__.select().where(self.__class__.user == self.user).count()

            if user_token_count >= app.config['MAX_TOKENS']:
                raise ValueError( # TODO: Is ValueError really the most fitting exception there is?
                    "User %s already has %d out of %d client certificate tokens." % (
                        self.user.name,
                        user_token_count,
                        app.config['MAX_TOKENS']
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
    not_before = poobrains.storage.fields.DateTimeField(null=True)
    not_after = poobrains.storage.fields.DateTimeField(null=True)
    notification = poobrains.storage.fields.IntegerField(form_widget=None, default=0) # number of last expiry warning sent

    
    def save(self, force_insert=False, only=None):

        if not self.id or force_insert:
            if self.__class__.select().where(self.__class__.user == self.user, self.__class__.name == self.name).count():
                raise ValueError("User %s already has a client certificate named '%s'." % (self.user.name, self.name))

        return super(ClientCert, self).save(force_insert=force_insert, only=only)

    
    @protected
    @poobrains.helpers.themed
    def view(self, mode='teaser', handle=None, **kwargs):

        """
        view function to be called in a request context
        """
        
        if self._meta.modes[mode] in ['create', 'update', 'delete']:

            f = self.form(mode)
            return poobrains.helpers.ThemedPassthrough(f.view('full'))

        return self


    @property
    def validity_period(self):
        return self.not_after - self.not_before


    @property
    def notification_dates(self):

        dates = []

        deltas = [
            datetime.timedelta(days=30),
            datetime.timedelta(days=3),
            datetime.timedelta(days=1),
        ]

        for delta in deltas:
            if self.validity_period > delta:
                dates.append(self.not_after - delta)

        return dates


class Owned(Administerable):

    class Meta:
        abstract = True
        permission_class = OwnedPermission


    owner = poobrains.storage.fields.ForeignKeyField(User, null=False)
    group = poobrains.storage.fields.ForeignKeyField(Group, null=True)
    access = poobrains.storage.fields.CharField(default='', form_widget=AccessField) # TODO: Add RegexpConstraint with ^r{0,1}u{0,1}d{0,1}$ ?

    def form(self, mode=None):

        op = self._meta.modes[mode]
        f = super(Owned, self).form(mode)

        if op == 'create':
            f.fields['owner'].value = g.user
            f.fields['group'].value = g.user.groups[0]

        return f


class NamedOwned(Owned, Named):
    
    class Meta:
        abstract = True


class Notification(poobrains.storage.Storable):

    to = poobrains.storage.fields.ForeignKeyField(User, related_name='notifications')
    created = poobrains.storage.fields.DateTimeField(default=datetime.datetime.now, null=False)
    read = poobrains.storage.fields.BooleanField(default=False)
    message = poobrains.md.MarkdownField()


class Page(Owned):

    path = poobrains.storage.fields.CharField(unique=True)
    title = poobrains.storage.fields.CharField()
    content = poobrains.md.MarkdownField()

    
    def instance_url(self, mode='full', quiet=None, **url_params):
        
        if mode == 'full':

            return app.site.get_view_url(self.__class__, mode=mode, quiet=quiet, path=self.path[1:], **url_params)

        return app.get_url(self.__class__, handle=self.handle_string, mode=mode, quiet=quiet, **url_params)


    @classmethod
    def class_view(cls, mode='teaser', handle=None, **kwargs):
        
        op = cls._meta.modes[mode]

        if op == 'create':
            print "CREATE!"
            instance = cls()

        elif op == 'read' and kwargs.has_key('path'):

            path = '/%s' % kwargs['path']
            instance = cls.get(cls.path == path)

        else:
            try:
                instance = cls.load(handle)
            except ValueError as e:
                raise cls.DoesNotExist("This isn't even the right type!")

        return instance.view(mode=mode, handle=handle, **kwargs)


app.site.add_view(Page, '/<regex(".*"):path>', mode='full')


@app.cron
def bury_tokens():

    deathwall = datetime.datetime.now() - datetime.timedelta(seconds=app.config['TOKEN_VALIDITY'])

    q = ClientCertToken.delete().where(
        (ClientCertToken.created <= deathwall) | (ClientCertToken.redeemed == 1)
    )

    count = q.execute()

    msg = "Deleted %d dead client certificate tokens." % count
    click.secho(msg, fg='green')
    app.logger.info(msg)


@app.cron
def notify_dying_cert_owners():

    now = datetime.datetime.now()
    affected_users = set()

    count_expired = 0
    count_impending_doom = 0

    for cert in ClientCert.select():

        if cert.notification > len(cert.notification_dates): # means expiry notification was already sent
            pass

        elif len(cert.notification_dates) == cert.notification:
            
            death_in = cert.not_after - now
            days = death_in.days
            hours = death_in.seconds // 3600
            minutes = (death_in.seconds - hours * 3600) // 60
            other_cert_count = cert.user.clientcerts.where(ClientCert.not_after > now).count() - 1

            message = """
### Client certificate for site {site_name} has expired! ###

*Your client certificate '{cert_name}' expired on {expiry_date}.*

You have {other_cert_count} other valid certificates on this site.
            """.format(
                site_name=app.config['SITE_NAME'],
                cert_name=cert.name,
                expiry_date=cert.not_after,
                other_cert_count=other_cert_count
            )

            cert.user.notify(message)
            click.echo("Notified user '%s' about expired certificate '%s'" % (cert.user.name, cert.name))
            affected_users.add(cert.user)
            count_expired += 1

            cert.notification += 1
            cert.save()

        elif cert.notification_dates[cert.notification] <= now:
        
            #TODO: DRY!
            death_in = cert.not_after - now
            days = death_in.days
            hours = death_in.seconds // 3600
            minutes = (death_in.seconds - hours * 3600) // 60
            other_cert_count = cert.user.clientcerts.where(ClientCert.not_after > now).count() - 1

            message = """
### Client certificate expiry warning for {site_name} ###

*Your client certificate '{cert_name}' will expire in {days} days,  {hours} hours, {minutes} minutes.*

You have {other_cert_count} other valid certificates on this site.
            """.format(
                site_name=app.config['SITE_NAME'],
                cert_name=cert.name,
                days=days,
                hours=hours,
                minutes=minutes,
                other_cert_count=other_cert_count
            )

            cert.user.notify(message)
            click.echo("Notified user '%s' about impending expiry of certificate '%s'" % (cert.user.name, cert.name))

            affected_users.add(cert.user)
            count_impending_doom += 1

            cert.notification += 1
            cert.save()

    click.secho("Notified %d users about %d certificates that will soon expire and %d that have expired." % (len(affected_users), count_impending_doom, count_expired), fg='green')
