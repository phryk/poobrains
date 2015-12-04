# external imports
import datetime
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
    token = poobrains.form.fields.ObfuscatedText(label='Token')
    keygen = poobrains.form.fields.Keygen()
    submit = poobrains.form.Button('submit', label='Generate Certificate')


class ClientCertToken(poobrains.storage.Storable):

    validity = None
    created = poobrains.storage.fields.DateTimeField(default=datetime.datetime.now)
    token = poobrains.storage.fields.CharField(unique=True)


    def __init__(self, *args, **kw):

        self.validity = poobrains.app.config['TOKEN_VALIDITY']
        super(ClientCertToken, self).__init__(*args, **kw)


class ClientCert(poobrains.storage.Storable):

    user = poobrains.storage.fields.ForeignKeyField(User)
    common_name = poobrains.storage.fields.CharField(unique=True)
    created = poobrains.storage.fields.DateTimeField(default=datetime.datetime.now)
    valid_till = poobrains.storage.fields.DateTimeField()



@poobrains.app.route('/cert/')
@poobrains.rendering.render()
@is_secure
def cert_form():

    return ClientCertForm()


@poobrains.app.route('/cert/', methods=['POST'])
@poobrains.rendering.render()
@is_secure
def cert_handle():

    poobrains.app.logger.debug(flask.request.form)

    token = ClientCertToken.get(ClientCertToken.token == flask.request.form['token'])
    poobrains.app.loger.debug(token)

    return poobrains.rendering.RenderString("Poof.")


#self.add_url_rule('/cert/', 'cert_form', cert_form)
#self.add_url_rule('/cert/', 'cert_handle', cert_handle, methods=['POST'])


