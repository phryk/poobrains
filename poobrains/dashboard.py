# -*- coding: utf-8 -*-

import OpenSSL as openssl

import flask
import poobrains


class Dashboard(poobrains.auth.Protected):

    user = None
    cert_table = None
    pgp_update_url = None

    def __init__(self, **kwargs):

        self.user = flask.g.user
        self.title = self.user.name

        if len(flask.request.environ['SSL_CLIENT_CERT']):
            cert_current = openssl.crypto.load_certificate(openssl.crypto.FILETYPE_PEM, flask.request.environ['SSL_CLIENT_CERT'])
        else:
            cert_current = None

        self.cert_table = poobrains.rendering.Table(columns=['Name', 'Fingerprint', 'Actions'])
        for cert_info in self.user.clientcerts:

            if cert_current and cert_info.fingerprint == cert_current.digest('sha512').replace(':', ''):
                classes = 'active'
            else:
                classes = None

            actions = poobrains.rendering.Menu('certificate-actions')
            actions.append(cert_info.url('delete'), 'Delete')

            self.cert_table.append(cert_info.name, cert_info.fingerprint, actions,_classes=classes)

        self.pgp_update_url = PubkeyForm.url('full')

poobrains.app.site.add_view(Dashboard, '/~', endpoint='dashboard', mode='full')


class PubkeyForm(poobrains.form.Form):

    pubkey = poobrains.form.fields.File()
    submit = poobrains.form.Button('submit', label='Update key')

    def __init__(self, handle=None, user=None, **kwargs):

        super(PubkeyForm, self).__init__(**kwargs)

        if user is not None:
            self.user = user
        else:
            self.user = flask.g.user

    
    def handle(self, submit):

        poobrains.app.debugger.set_trace()

        pubkey = self.fields['pubkey'].value.read()
        crypto = poobrains.mailing.getgpg()
        x = crypto.import_keys(pubkey)
        flask.flash("Imported new key!")

        return self

poobrains.app.site.add_view(PubkeyForm, '/~/pgp', mode='full')
