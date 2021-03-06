# -*- coding: utf-8 -*-

import collections
import OpenSSL as openssl

import werkzeug
import flask

#import poobrains
from poobrains import app, g
import poobrains.helpers
import poobrains.mailing
import poobrains.rendering
import poobrains.form
import poobrains.storage
import poobrains.auth

import time
import datetime

class Dashbar(poobrains.rendering.Container):

    user = None

    def __init__(self, user, **kwargs):

        super(Dashbar, self).__init__(**kwargs)

        self.user = user

        menu = poobrains.rendering.Menu('dashbar-actions')

        try:
            user.permissions['read'].check(g.user)
            menu.append(g.user.url('full'), "%s@%s" % (user.name, app.config['SITE_NAME']))
        except poobrains.auth.AccessDenied:
            pass

        try:
            poobrains.auth.AccessAdminArea.check(g.user)
            menu.append(flask.url_for('admin.admin_index'), 'Admin Area')
        except poobrains.auth.AccessDenied:
            pass

        try:
            PGPControl.permissions['read'].check(g.user)
            menu.append(PGPControl.url('full', handle=self.user.handle_string), 'PGP Management')
        except poobrains.auth.AccessDenied:
            pass

        try:
            CertControl.permissions['read'].check(g.user)
            menu.append(CertControl.url('full', handle=self.user.handle_string), 'Certificate Management')
        except poobrains.auth.AccessDenied:
            pass

        try:
            NotificationControl.permissions['read'].check(g.user)
            notification_count = self.user.notifications_unread.count()
            if notification_count == 1:
                menu.append(NotificationControl.url('full', handle=self.user.handle_string), '1 unread notification')
            else:
                menu.append(NotificationControl.url('full', handle=self.user.handle_string), '%d unread notifications' % notification_count)
        except poobrains.auth.AccessDenied:
            pass

        self.items.append(menu)


@app.box('dashbar')
def dashbar():
    user = g.user
    if user.id != 1: # not "anonymous"
        return Dashbar(g.user)


class CertControl(poobrains.auth.Protected):

    class Meta:

        modes = collections.OrderedDict([
            ('add', 'create'),
            ('full', 'read'),
            ('delete', 'delete')
        ])

    user = None
    cert_table = None

    def __init__(self, handle=None, cert_handle=None, **kwargs):

        super(CertControl, self).__init__(handle=handle, **kwargs)
        self.user = poobrains.auth.User.load(handle)
        #self.title = self.user.name

        self.pre = poobrains.rendering.Menu('certtoken-add')
        self.pre.append(self.url(mode='add'), 'Add new')

        if len(flask.request.environ['SSL_CLIENT_CERT']):
            cert_current = openssl.crypto.load_certificate(openssl.crypto.FILETYPE_PEM, flask.request.environ['SSL_CLIENT_CERT'])
        else:
            cert_current = None

        self.cert_table = poobrains.rendering.Table(columns=['Name', 'Key length', 'Fingerprint', 'Actions'])
        for cert_info in self.user.clientcerts:

            if cert_current and cert_info.fingerprint == cert_current.digest('sha512').replace(':', ''):
                classes = 'active'
            else:
                classes = None

            actions = poobrains.rendering.Menu('certificate-actions')
            actions.append(CertControl.url(mode='delete', handle=handle, cert_handle=cert_info.handle_string), 'Delete')

            self.cert_table.append(cert_info.name, cert_info.keylength, cert_info.fingerprint, actions,_classes=classes)
    
    @poobrains.helpers.themed
    def view(self, handle=None, cert_handle=None, mode='full', **kwargs):

        if mode == 'add':
            token = poobrains.auth.ClientCertToken()
            token.user = self.user
            f = token.form('add')
            f.fields['user'].readonly = True
            f.created = poobrains.form.fields.Value(value=datetime.datetime.now())
            f.redeemed = poobrains.form.fields.Value(value=False)

            r = poobrains.helpers.ThemedPassthrough(f.view(**kwargs))

            if flask.request.method == 'POST':
                return flask.redirect(CertControl.url(mode='full', handle=handle))

            return r

        if cert_handle is not None and mode == 'delete':
            cert = poobrains.auth.ClientCert.load(cert_handle)
            if self.user == cert.user:
                cert.permissions['read'].check(g.user)
                r = cert.form('delete').view(handle=cert_handle, **kwargs)

                if flask.request.method in ['POST', 'DELETE']:
                    return flask.redirect(CertControl.url(mode='full', handle=handle))

                return poobrains.helpers.ThemedPassthrough(r)

        return poobrains.helpers.ThemedPassthrough(super(CertControl, self).view(handle=handle, cert_handle=cert_handle, mode=mode, **kwargs))

app.site.add_view(CertControl, '/~<handle>/cert/', mode='full', endpoint='certcontrol')
app.site.add_view(CertControl, '/~<handle>/cert/add/', mode='add', endpoint='certcontrol_add')
app.site.add_view(CertControl, '/~<handle>/cert/<cert_handle>', mode='delete', endpoint='certcontrol_delete')


class PGPControl(poobrains.auth.Protected):

    user = None

    def __init__(self, handle=None, **kwargs):

        super(PGPControl, self).__init__(**kwargs)
        self.user = poobrains.auth.User.load(handle)


    def view(self, handle=None, **kwargs):

        r = super(PGPControl, self).view(handle=handle, **kwargs) # checks permissions
        return PGPForm(handle=handle).view(handle=handle, **kwargs)
        #return r

app.site.add_view(PGPControl, '/~<handle>/pgp', mode='full')

class PGPForm(poobrains.form.Form):

    current_key = None
    pubkey = poobrains.form.fields.File()
    submit = poobrains.form.Button('submit', label='Update key')

    def __init__(self, handle=None, **kwargs):

        super(PGPForm, self).__init__(**kwargs)
        self.user = poobrains.auth.User.load(handle)
        self.current_key = poobrains.form.fields.Message(value="Your current key is: %s" % self.user.pgp_fingerprint)
        self.fields.order = ['current_key', 'pubkey']
   

    def process(self, submit):

        pubkey = self.fields['pubkey'].value.read()
        crypto = poobrains.mailing.getgpg()
        result = crypto.import_keys(pubkey)

        if len(result.fingerprints) == 1:

            self.user.pgp_fingerprint = result.fingerprints[0]
            self.user.save()
            flask.flash(u"Imported new key and assigned it to you.")

        elif len(result.fingerprints) > 1:

            flask.flash(u"Keyfile may only hold a single key.")

        else:
            # Fun fact: I'm more proud of this error message than half my code.
            flask.flash(u"Something went wrong when importing your new key. A pack of lazy raccoons has been dispatched to look at your plight in disinterested amusement.")
            app.logger.error("GPG key import error: %s" % result.stderr)

        return flask.redirect(flask.request.path) # reload page to show flash()es



class NotificationControl(poobrains.auth.Protected):

    results = None
    pagination = None

    def __init__(self, handle=None, offset=0, **kwargs):

        super(NotificationControl, self).__init__(**kwargs)
        user = poobrains.auth.User.load(handle)

        self.form = NotificationForm()

        pagination = poobrains.storage.Pagination([user.notifications_unread, user.notifications.where(poobrains.auth.Notification.read == True)], offset, 'site.notification_offset', handle=handle)

        self.results = pagination.results
        self.pagination = pagination.menu

        self.table = poobrains.rendering.Table(css_class='notifications')

        for notification in pagination.results:

            classes = 'read inactive' if notification.read else 'unread active'
            mark_checkbox = poobrains.form.fields.Checkbox(form=self.form, name='mark', label='', type=poobrains.form.types.StorableInstanceParamType(poobrains.auth.Notification), choices=[(notification, None)], multi=True)

            self.table.append(notification, mark_checkbox, _classes=classes)


    @poobrains.helpers.themed
    def view(self, handle=None, **kwargs):

        if flask.request.method in ['POST', 'DELETE']:

            values = flask.request.form.get(self.form.name, werkzeug.datastructures.MultiDict())

            try:
                self.form.bind(values, werkzeug.datastructures.MultiDict())
            except poobrains.errors.CompoundError as e:
                for error in e.errors:
                    flask.flash(e.message, 'error')

            else:
        
                if len(self.form.fields['mark'].value): # means we have to issue a query
                    self.form.process(flask.request.form['submit'][len(self.form.ref_id)+1:])
                    return flask.redirect(flask.request.path)


        return self


app.site.add_view(NotificationControl, '/~<handle>/notifications/', mode='full')
app.site.add_view(NotificationControl, '/~<handle>/notifications/+<int:offset>', mode='full', endpoint='notification_offset')


class NotificationForm(poobrains.form.Form):

    mark = poobrains.form.fields.Checkbox(type=poobrains.form.types.StorableInstanceParamType(poobrains.auth.Notification), multi=True)
    mark_read = poobrains.form.Button('submit', label='Mark as read')
    delete = poobrains.form.Button('submit', label='Delete')

    def process(self, submit):

        for handle in self.fields['mark'].value:

            instance = poobrains.auth.Notification.load(handle)

            if self.controls['mark_read'].value:
                flask.flash(u"Marking notification %d as read." % instance.id)
                instance.read = True
                instance.save()

            elif self.controls['delete'].value:
                flask.flash(u"Deleting notification %d." % instance.id)
                instance.delete_instance()

        return self
