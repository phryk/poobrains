# external imports
import datetime
import flask

# local imports
import form
import storage


class User(storage.Storable):

    name = storage.fields.CharField(unique=True)
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


class ClientCertForm(form.Form):
    
    passphrase = form.fields.ObfuscatedText()



class ClientCertToken(storage.Storable):

    validity = None
    created = storage.fields.DateTimeField(default=datetime.datetime.now)
    token = storage.fields.CharField(unique=True)


    def __init__(self, *args, **kw):

        self.validity = flask.current_app.config['TOKEN_VALIDITY']
        super(ClientCertToken, self).__init__(*args, **kw)
