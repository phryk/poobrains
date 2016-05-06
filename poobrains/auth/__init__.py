# -*- coding: utf-8 -*-

# external imports
import M2Crypto #import X509, EVP
import pyspkac #import SPKAC
import time
import datetime
import werkzeug
import flask

from functools import wraps

# local imports
import poobrains


def is_secure(f):

    """
    decorator. Denies access if an url is accessed without TLS.
    """

    @wraps(f)
    def substitute():

        if flask.request.is_secure:
            return f()

        else:
            flask.abort(403, "You are trying to do naughty things without protection.")

    return substitute


class User(poobrains.storage.Storable):

    name = poobrains.storage.fields.CharField(unique=True)
    groups = None
    permissions = None


    def __init__(self, *args, **kwargs):

        super(User, self).__init__(*args, **kwargs)

        self.password_modified = False
        self.groups = {}
        self.permissions = {}


    def __setattr__(self, name, value):

        if name == 'password':
            self.password_modified = True

        super(User, self).__setattr__(name, value)


    def __repr__(self):

        if self.id is not None:
            return '<Poobrains User %d: %s>' % (self.id, self.name)

        return '<Poobrains User, unsaved>'


class ClientCertForm(poobrains.form.Form):
    
    #passphrase = poobrains.form.fields.ObfuscatedText()
    title = "Be safe, certificatisize yourself!"
    token = poobrains.form.fields.ObfuscatedText(label='Token')
    key = poobrains.form.fields.Keygen()
    submit = poobrains.form.Button('submit', label='Generate Certificate')


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


@poobrains.app.route('/cert/')
@poobrains.rendering.render()
@is_secure
def cert_form():

    f = ClientCertForm()
    flask.session['key_challenge'] = f.fields['key'].challenge
    return f


@poobrains.app.route('/cert/', methods=['POST'])
@poobrains.rendering.render()
@is_secure
def cert_handle():

    try:
        token = ClientCertToken.get(ClientCertToken.token == flask.request.form['token'])

    except Exception as e:
        return poobrains.rendering.RenderString("No such token.")


    try:

        ca_key = M2Crypto.EVP.load_key(poobrains.app.config['CA_KEY'])
        ca_cert = M2Crypto.X509.load_cert(poobrains.app.config['CA_CERT'])

    except Exception as e:

        return poobrains.rendering.RenderString("Plumbing issue. Invalid CA_KEY or CA_CERT.")


    spkac = pyspkac.SPKAC(flask.request.form['key'], flask.session['key_challenge'], CN=token.user.name, Email='fnord@fnord.fnord')
    spkac.push_extension(M2Crypto.X509.new_extension('keyUsage', 'digitalSignature, keyEncipherment, keyAgreement', critical=True))
    spkac.push_extension(M2Crypto.X509.new_extension('extendedKeyUsage', 'clientAuth, emailProtection, nsSGC'))

    spkac.subject.C = ca_cert.get_subject().C

    not_before = int(time.time())
    not_after = not_before + poobrains.app.config['CERT_LIFETIME']

    client_cert = spkac.gen_crt(ca_key, ca_cert, 44, not_before, not_after, hash_algo='sha512')
    cert_info = ClientCert()
    cert_info.name = token.name
    cert_info.user = token.user
    #cert_info.pubkey = client_cert.get_pubkey().as_pem(cipher=None) # We don't even need the pubkey. subject distinguished name should™ work just as well.
    cert_info.subject_name = unicode(client_cert.get_subject())
    poobrains.app.logger.debug('client cert subject:')
    poobrains.app.logger.debug(type(client_cert.get_subject()))
    poobrains.app.logger.debug(client_cert.get_subject())
    cert_info.save()

    r = werkzeug.wrappers.Response(client_cert.as_pem())
    r.mimetype = 'application/x-x509-user-cert'
    return r
