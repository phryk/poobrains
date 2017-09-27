# -*- coding: utf-8 -*-

import collections
import os
import datetime
import functools
import peewee
import OpenSSL
import gnupg
import flask
import click
import jinja2

from playhouse import db_url
db_url.schemes['sqlite'] = db_url.schemes['sqliteext'] # Make sure we get the extensible sqlite database, so we can make regular expressions case-sensitive. see https://github.com/coleifer/peewee/issues/1221

from poobrains import app, project_name
import poobrains.helpers
import poobrains.storage
import poobrains.auth

from poobrains.form import types


def mkconfig(template, **values):

    template_dir = os.path.join(app.poobrain_path, 'cli', 'templates')
    jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))
    template = jinja_env.get_template('%s.jinja' % template)

    return template.render(**values)


def fake_before_request(function):

    @functools.wraps(function)
    def substitute(*args, **kwargs):

        flask.g.user = poobrains.auth.User.get(poobrains.auth.User.id == 2) # load root user

        return function(*args, **kwargs)

    return substitute


@app.cli.command()
def test():
    click.echo("Running test command!")


@app.cli.command()
@click.option('--domain', prompt="Domain this site will be run under?", default="localhost")
@click.option('--database', default="sqlite:///%s.db" % project_name) # NOTE: If you change this you'll have to change in the main __init__.py as well
@click.option('--keylength', prompt="Length for cryptographic keys (in bits)", default=4096)
@click.option('--deployment', prompt="Please choose your way of deployment for automatic config generation", type=click.Choice(['uwsgi+nginx', 'custom']), default='uwsgi+nginx')
@click.option('--deployment-os', prompt="What OS are you deploying to?", type=click.Choice(['linux', 'freebsd']), default=lambda: os.uname()[0].lower())
@click.option('--mail-address', prompt="Site email address") # FIXME: needs a regexp check
@click.option('--mail-server', prompt="Site email server") # FIXME: needs regexp check, maybe connection check
@click.option('--mail-port', prompt="Site email server port", type=int)
@click.option('--mail-user', prompt="Site email account username")
@click.option('--mail-password', prompt="Site email password")
@click.option('--admin-mail-address', prompt="Admin email address") # FIXME: needs a regexp check
@click.option('--admin-cert-name', prompt="Admin login certificate name", default="%s-initial" % project_name) # FIXME: needs a regexp check
@click.option('--gnupg-homedir', prompt="gnupg homedir, relative to project root (corresponds to gpgs' --homedir)", default="gnupg")
@click.option('--gnupg-binary', default=None)
@click.option('--gnupg-passphrase', prompt="gnupg passphrase (used to create a keypair)", default=lambda: poobrains.helpers.random_string_light(64))
def install(**options):

        if click.confirm("Really execute installation procedure?"):

            options['project_name'] = project_name
            options['project_dir'] = app.site_path
            options['secret_key'] = poobrains.helpers.random_string_light(64) # cookie crypto key, config['SECRET_KEY']


            with click.progressbar(poobrains.storage.Model.class_children(), label="Creating tables", item_show_func=lambda x: x.__name__ if x else '') as models: # iterates through all non-abstract Models
                for model in models:
                    app.db.create_tables([model])

            click.echo("Database tables created!\n")

            click.echo("Creating Group 'anonsanonymous'…\n")
            anons = poobrains.auth.Group()
            anons.name = 'anonsanonymous'
            
            if not anons.save(force_insert=True):
                raise ShellException("Failed creating Group 'anonsanonymous'!")
            click.echo("Successfully created Group 'anonsanonymous'.\n")


            click.echo("Creating Group 'administrators' with all permissions granted…\n")
            admins = poobrains.auth.Group()
            admins.name = 'administrators'
            
            for cls in poobrains.auth.Permission.class_children():
                choice_values = [x[0] for x in cls.choices]
                if 'grant' in choice_values:
                    access = 'grant'
                else:
                    click.echo("Don't know what access value to use for permission '%s', skipping.\n" % cls.__name__)
                    break

                #click.echo("Adding permission %s: %s\n" % (cls.__name__, access))
                admins.own_permissions[cls.__name__] = access
            
            if not admins.save(force_insert=True):
                raise ShellException("Failed creating Group 'administrators'!")

            click.echo("Successfully saved Group 'administrators'.\n")


            anon = poobrains.auth.User()
            anon.name = 'anonymous'
            #anon.id = 1 # Should theoretically always happen, but let's make sure anyways; This fucks up postgresql's stupid SERIAL sequence thing
            anon.groups.append(anons)
            if not anon.save(force_insert=True):
                raise ShellException("Failed creating User 'anonymous'!")
            click.echo("Successfully created User 'anonymous'.\n")

            click.echo("Creating administrator account…\n")
            root = poobrains.auth.User()
            root.name = 'root'
            root.mail = options['admin_mail_address']
            root.groups.append(admins) # Put 'administrator' into group 'administrators'

            if not root.save():
                
                raise ShellException("Couldn't save administrator. Please try again or fix according bugs.")

            click.echo("Successfully created administrator account.\n")

            t = poobrains.auth.ClientCertToken()
            t.user = root
            t.cert_name = options['admin_cert_name']

            if t.save():
                click.echo("Admin certificate token is: %s\n" % click.style(t.token, fg="cyan", bold=True))

            
            click.echo("We'll now configure GPG for sending encrypted mail.\n")

            if options['gnupg_binary']:
                gpg = gnupg.GPG(binary=options['gnupg_binary'], homedir=options['gnupg_homedir'])
            else: # let the gnupg module figure it out
                gpg = gnupg.GPG(homedir=options['gnupg_homedir'])


            click.echo("Creating trustdb, if it doesn't exist\n")
            gpg.create_trustdb()
            site_gpg_info = gpg.gen_key_input(
                name_email = options['mail_address'],
                key_type = 'RSA',
                key_length = options['keylength'],
                key_usage = 'encrypt,sign',
                passphrase = options['gnupg_passphrase']
            )

            click.echo("Generating PGP key for this site. This will probably take a pretty long while. Go get a sammich.\n")
            gpg.gen_key(site_gpg_info)
            
            click.echo("Probably created site PGP key! \o/")

            config = mkconfig('config', **options) 
            config_fd = open(os.path.join(app.root_path, 'config.py'), 'w')
            config_fd.write(config)
            config_fd.close()

            if options['deployment'] == 'uwsgi+nginx':

                uwsgi_ini = mkconfig('uwsgi', **options)
                uwsgi_ini_filename = '%s.ini' % options['project_name']
                uwsgi_ini_fd = open(os.path.join(app.root_path, uwsgi_ini_filename), 'w')
                uwsgi_ini_fd.write(uwsgi_ini)
                uwsgi_ini_fd.close()
                click.echo("UWSGI .ini file was written to %s" % click.style(uwsgi_ini_filename, fg='green'))

                nginx_conf = mkconfig('nginx', **options)
                nginx_conf_filename = '%s.nginx.conf' % options['project_name']
                nginx_conf_fd = open(os.path.join(app.root_path, nginx_conf_filename), 'w')
                nginx_conf_fd.write(nginx_conf)
                nginx_conf_fd.close()
                click.echo("nginx config snippet was written to %s" % click.style(nginx_conf_filename, fg='green'))

            click.echo("Installation complete!\n")


@app.cli.command()
@click.option('--lifetime', prompt="How long should this CA live (in seconds, 0 means infinite)?", default=0)
def minica(lifetime):

    click.echo("Generating keypair.")

    keypair = OpenSSL.crypto.PKey()
    keypair.generate_key(OpenSSL.crypto.TYPE_RSA, app.config['CRYPTO_KEYLENGTH'])


    click.echo("Generating certificate")
    cert = OpenSSL.crypto.X509()
    cert.get_issuer().commonName = app.config['DOMAIN'] # srsly pyOpenSSL?
    cert.get_issuer().C = 'AQ'
    cert.get_issuer().L = 'Fnordpol'
    cert.get_issuer().O = 'Erisian Liberation Front'
    cert.get_issuer().OU = 'Cyber Confusion Center'
    #cert.get_subject().commonName = app.config['DOMAIN'] # srsly pyOpenSSL?
    cert.set_subject(cert.get_issuer())
    cert.set_pubkey(keypair)
    cert.gmtime_adj_notBefore(0)
    if lifetime == 0:
        cert.set_notAfter('99991231235959Z') # "indefinitely valid" as defined in RFC 5280 4.1.2.5.
    else:
        cert.gmtime_adj_notAfter(lifetime)
    
    extensions = []
    extensions.append(OpenSSL.crypto.X509Extension('basicConstraints', True, "CA:TRUE, pathlen:0"))
    extensions.append(OpenSSL.crypto.X509Extension('keyUsage', True, 'digitalSignature, keyEncipherment, dataEncipherment, keyAgreement, keyCertSign, cRLSign'))
    cert.add_extensions(extensions)

    # finally, sign the certificate with the private key
    cert.sign(keypair, b"sha512")

    tls_dir = os.path.join(app.root_path, 'tls')
    if os.path.exists(tls_dir):
        click.secho("Directory/file '%s' already exists. Move or delete it and re-run." % tls_dir, fg='red')
        raise click.Abort()


    click.echo("Creating directory '%s'." % tls_dir)
    os.mkdir(os.path.join(tls_dir))

    click.echo("Creating certificate file")
    cert_pem = OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)
    fd = open(os.path.join(tls_dir, 'cert.pem'), 'w')
    fd.write(cert_pem)
    fd.close()

    click.echo("Private Key:")
    key_pem = OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM, keypair)
    fd = open(os.path.join(tls_dir, 'key.pem'), 'w')
    fd.write(key_pem)
    fd.close()

    click.echo("All done! :)")


@app.cli.command()
@click.argument('storable', type=types.STORABLE)
@fake_before_request
def add(storable):
        
        instance = storable()

        click.echo("Addding %s...\n" % (storable.__name__,))
        for field in storable._meta.sorted_fields:

            if not isinstance(field, peewee.PrimaryKeyField):

                fieldtype = field.form_class().type
                if fieldtype is None:
                    click.secho("Falling back to string for field '%s' % field.name", fg='yellow')
                    fieldtype = types.STRING

                default = None

                if fieldtype == types.DATETIME:
                    default = datetime.datetime.now()

                value = click.prompt(field.name, type=fieldtype, default=default)

                if value != '': # Makes models fall back to defaults for this field
                    setattr(instance, field.name, value) # TODO type enforcement

        instance.save(force_insert=True)

@app.cli.command()
@click.argument('storable', type=types.STORABLE)
@fake_before_request
def list(storable):

    for instance in storable.select():

        print "%s: %s - %s" % (instance.handle_string, instance.title, instance)


@app.cli.command()
@click.argument('storable', type=types.STORABLE)
@fake_before_request
def delete(storable):

    instance = click.prompt("%s handle" % storable.__name__, type=types.StorableInstanceParamType(storable))
    click.echo(instance)
    if click.confirm("Really delete this %s?" % storable.__name__):

        handle = instance.handle_string

        if instance.delete_instance():
            click.echo("Deleted %s %s" % (storable.__name__, handle))

        else:
            click.echo("Could not delete %s %s." % (storable.__name__, handle))


@app.cli.command()
def cron():

    app.cron_run()
