# -*- coding: utf-8 -*-

import collections
import OpenSSL as openssl

import flask
import poobrains


class Dashbar(poobrains.rendering.Container):

    user = None

    def __init__(self, user, **kwargs):

        super(Dashbar, self).__init__(**kwargs)

        self.user = user
        self.items.append(poobrains.rendering.RenderString("%s@%s" % (user.name, poobrains.app.config['SITE_NAME'])))

        menu = poobrains.rendering.Menu('dashbar-actions')
        menu.append(PGPControl.url('full', handle=self.user.handle_string), 'PGP Management')
        menu.append(CertControl.url('full', handle=self.user.handle_string), 'Certificate Management')

        self.items.append(menu)


@poobrains.app.box('dashbar')
def dashbar():
    user = flask.g.user
    if user.id != 1: # not "anonymous"
        return Dashbar(flask.g.user)


class CertControl(poobrains.auth.Protected):

    class Meta:

        ops = collections.OrderedDict([
            ('r', 'read'),
            ('d', 'delete')
        ])

        modes = collections.OrderedDict([
            ('full', 'r'),
            ('delete', 'd')
        ])

    user = None
    cert_table = None

    def __init__(self, handle=None, cert_handle=None, **kwargs):

        super(CertControl, self).__init__(**kwargs)
        self.user = poobrains.auth.User.load(handle)
        #self.title = self.user.name

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
    def view(self, handle=None, cert_handle=None, **kwargs):

        if cert_handle is not None:
            cert = poobrains.auth.ClientCert.load(cert_handle)
            if self.user == cert.user:
                cert.permissions['read'].check(flask.g.user)
                r = cert.form('delete').view(handle=cert_handle, **kwargs)

                if flask.request.method in ['POST', 'DELETE']:
                    return flask.redirect(CertControl.url(mode='full', handle=handle))

                return poobrains.helpers.ThemedPassthrough(r)

        return poobrains.helpers.ThemedPassthrough(super(CertControl, self).view(handle=handle, cert_handle=cert_handle, **kwargs))

poobrains.app.site.add_view(CertControl, '/~<handle>/cert/', endpoint='certcontrol', mode='full')
poobrains.app.site.add_view(CertControl, '/~<handle>/cert/<cert_handle>', mode='delete')


class PGPControl(poobrains.auth.Protected):

    user = None

    def __init__(self, handle=None, **kwargs):

        super(PGPControl, self).__init__(**kwargs)
        self.user = poobrains.auth.User.load(handle)


    def view(self, handle=None, **kwargs):

        r = super(PGPControl, self).view(handle=handle, **kwargs) # checks permissions
        return PGPForm(handle=handle).view(handle=handle, **kwargs)
        #return r

poobrains.app.site.add_view(PGPControl, '/~<handle>/pgp', mode='full')

class PGPForm(poobrains.form.Form):

    current_key = None
    pubkey = poobrains.form.fields.File()
    submit = poobrains.form.Button('submit', label='Update key')

    def __init__(self, handle=None, **kwargs):

        super(PGPForm, self).__init__(**kwargs)
        self.user = poobrains.auth.User.load(handle)
        self.current_key = poobrains.form.fields.Message(value="Your current key is: %s" % self.user.pgp_fingerprint)
        self.fields.order = ['current_key', 'pubkey']
   

    def handle(self, submit):

        pubkey = self.fields['pubkey'].value.read()
        crypto = poobrains.mailing.getgpg()
        x = crypto.import_keys(pubkey)
        flask.flash("Imported new key!")

        return self
