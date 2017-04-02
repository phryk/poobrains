# -*- coding: utf-8 -*-

import flask
import poobrains


class Dashboard(poobrains.auth.Protected):

    user = None

    def __init__(self, **kwargs):

        self.user = flask.g.user
        self.title = self.user.name


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

    
    def handle(self):

        poobrains.app.debugger.set_trace()

        pubkey = self.fields['pubkey'].value.read()
        crypto = poobrains.mailing.getgpg()
        x = crypto.import_keys(pubkey)
        flask.flash("Imported new key!")

        return self

poobrains.app.site.add_view(PubkeyForm, '/~/pgp', mode='full')
