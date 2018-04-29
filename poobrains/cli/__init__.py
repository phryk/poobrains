# -*- coding: utf-8 -*-

import os
import datetime
import functools
import codecs
import peewee
import OpenSSL
import gnupg
import flask
import click
import jinja2

from click import argument, option, echo, secho, confirm
from playhouse import db_url
db_url.schemes['sqlite'] = db_url.schemes['sqliteext'] # Make sure we get the extensible sqlite database, so we can make regular expressions case-sensitive. see https://github.com/coleifer/peewee/issues/1221

from poobrains import app, project_name
import poobrains.helpers
import poobrains.storage
import poobrains.auth
import poobrains.svg

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

    if confirm(
        "This will run through installation and a range of tests, " +
        click.style("all current data will be lost!\n", fg='red') +
        click.style("!!!DO NOT DO THIS IN PRODUCTION!!!", bg='red', fg='black')
    ):

        from poobrains import testing
        testing.run_all()


@app.cli.command()
@option('--domain', prompt="Domain this site will be run under?", default="localhost")
@option('--database', default="sqlite:///%s.db" % project_name) # NOTE: If you change this you'll have to change in the main __init__.py as well
@option('--keylength', prompt="Length for cryptographic keys (in bits)", default=4096)
@option('--deployment', prompt="Please choose your way of deployment for automatic config generation", type=click.Choice(['uwsgi+nginx', 'custom']), default='uwsgi+nginx')
@option('--deployment-os', prompt="What OS are you deploying to?", type=click.Choice(['linux', 'freebsd']), default=lambda: os.uname()[0].lower())
@option('--mail-address', prompt="Site email address") # FIXME: needs a regexp check
@option('--mail-server', prompt="Site email server") # FIXME: needs regexp check, maybe connection check
@option('--mail-port', prompt="Site email server port", type=int)
@option('--mail-user', prompt="Site email account username")
@option('--mail-password', prompt="Site email password")
@option('--admin-mail-address', prompt="Admin email address") # FIXME: needs a regexp check
@option('--admin-cert-name', prompt="Admin login certificate name", default="%s-initial" % project_name) # FIXME: needs a regexp check
@option('--gnupg-homedir', prompt="gnupg homedir, relative to project root (corresponds to gpgs' --homedir)", default="gnupg")
@option('--gnupg-binary', default=None)
@option('--gnupg-passphrase', prompt="gnupg passphrase (used to create a keypair)", default=lambda: poobrains.helpers.random_string_light(64))
def install(**options):

        if confirm("Really execute installation procedure?"):

            options['project_name'] = project_name
            options['project_dir'] = app.site_path
            options['secret_key'] = poobrains.helpers.random_string_light(64) # cookie crypto key, config['SECRET_KEY']


            #with click.progressbar(poobrains.storage.Model.class_children(), label="Creating tables", item_show_func=lambda x: x.__name__ if x else '') as models: # iterates through all non-abstract Models
            #    for model in models:
            #        app.db.create_tables([model])

            app.db.create_tables(poobrains.storage.Model.class_children())

            echo("Database tables created!\n")

            echo("Creating Group 'anonsanonymous'…\n")
            anons = poobrains.auth.Group()
            anons.name = 'anonsanonymous'
            
            if not anons.save(force_insert=True):
                raise ShellException("Failed creating Group 'anonsanonymous'!")
            echo("Successfully created Group 'anonsanonymous'.\n")


            echo("Creating Group 'administrators'…\n")
            admins = poobrains.auth.Group()
            admins.name = 'administrators'
            
            if not admins.save(force_insert=True):
                raise ShellException("Failed creating Group 'administrators'!")

            with click.progressbar(poobrains.auth.Permission.class_children(), label="Giving 'administrators' ALL THE PERMISSIONS! \o/") as permissions:

                for permission in permissions:
                    choice_values = [x[0] for x in permission.choices]
                    if 'grant' in choice_values:
                        access = 'grant'
                    else:
                        echo("Don't know what access value to use for permission '%s', skipping.\n" % permission.__name__)
                        break

                    gp = poobrains.auth.GroupPermission()
                    gp.group = admins
                    gp.permission = permission.__name__
                    gp.access = access
                    gp.save(force_insert=True)
            

            echo("Success!\n")


            anon = poobrains.auth.User()
            anon.name = 'anonymous'
            #anon.id = 1 # Should theoretically always happen, but let's make sure anyways; This fucks up postgresql's stupid SERIAL sequence thing
            if not anon.save(force_insert=True):
                raise ShellException("Failed creating User 'anonymous'!")
            echo("Successfully created User 'anonymous'.\n")

            ug = poobrains.auth.UserGroup()
            ug.user = anon
            ug.group = anons
            if not ug.save(force_insert=True):
                raise ShellException("Failed to assign group to User 'anonymous'!")
            echo("Added user 'anonymous' to group 'anonsanonymous'.\n")

            echo("Creating administrator account…\n")
            root = poobrains.auth.User()
            root.name = 'root'
            root.mail = options['admin_mail_address']
            root.groups.append(admins) # Put 'administrator' into group 'administrators'

            if not root.save():
                
                raise ShellException("Couldn't save administrator. Please try again or fix according bugs.")

            echo("Successfully created administrator account.\n")
            
            ug = poobrains.auth.UserGroup()
            ug.user = root
            ug.group = admins
            if not ug.save(force_insert=True):
                raise ShellException("Failed to assign group to User 'root'!")
            echo("Added user 'root' to group 'administrators'.\n")

            t = poobrains.auth.ClientCertToken()
            t.user = root
            t.cert_name = options['admin_cert_name']

            if t.save():
                echo("Admin certificate token is: %s\n" % click.style(t.token, fg="cyan", bold=True))

            
            echo("We'll now configure GPG for sending encrypted mail.\n")

            if options['gnupg_binary']:
                gpg = gnupg.GPG(binary=options['gnupg_binary'], homedir=options['gnupg_homedir'])
            else: # let the gnupg module figure it out
                gpg = gnupg.GPG(homedir=options['gnupg_homedir'])


            echo("Creating trustdb, if it doesn't exist\n")
            gpg.create_trustdb()
            site_gpg_info = gpg.gen_key_input(
                name_email = options['mail_address'],
                key_type = 'RSA',
                key_length = options['keylength'],
                key_usage = 'encrypt,sign',
                passphrase = options['gnupg_passphrase']
            )

            echo("Generating PGP key for this site. This will probably take a pretty long while. Go get a sammich.\n")
            gpg.gen_key(site_gpg_info)
            
            echo("Probably created site PGP key! \o/")

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
                echo("UWSGI .ini file was written to %s" % click.style(uwsgi_ini_filename, fg='green'))

                nginx_conf = mkconfig('nginx', **options)
                nginx_conf_filename = '%s.nginx.conf' % options['project_name']
                nginx_conf_fd = open(os.path.join(app.root_path, nginx_conf_filename), 'w')
                nginx_conf_fd.write(nginx_conf)
                nginx_conf_fd.close()
                echo("nginx config snippet was written to %s" % click.style(nginx_conf_filename, fg='green'))

            echo("Installation complete!\n")


@app.cli.command()
@option('--lifetime', prompt="How long should this CA live (in seconds, 0 means infinite)?", default=0)
def minica(lifetime):

    echo("Generating keypair.")

    keypair = OpenSSL.crypto.PKey()
    keypair.generate_key(OpenSSL.crypto.TYPE_RSA, app.config['CRYPTO_KEYLENGTH'])


    echo("Generating certificate")
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
        secho("Directory/file '%s' already exists. Move or delete it and re-run." % tls_dir, fg='red')
        raise click.Abort()


    echo("Creating directory '%s'." % tls_dir)
    os.mkdir(os.path.join(tls_dir))

    echo("Creating certificate file")
    cert_pem = OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)
    fd = open(os.path.join(tls_dir, 'cert.pem'), 'w')
    fd.write(cert_pem)
    fd.close()

    echo("Private Key:")
    key_pem = OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM, keypair)
    fd = open(os.path.join(tls_dir, 'key.pem'), 'w')
    fd.write(key_pem)
    fd.close()

    echo("All done! :)")


@app.cli.command()
@argument('storable', type=types.STORABLE)
@fake_before_request
def add(storable):

    instance = storable()

    echo("Addding %s...\n" % (storable.__name__,))
    for field in storable._meta.sorted_fields:

        if not isinstance(field, peewee.AutoField):

            default = None

            if field.default:

                if callable(field.default):
                    default = field.default()
                else:
                    default = field.default

            elif field.type == types.DATETIME:
                default = datetime.datetime.now()
            
            elif field.type == types.BOOL:
                default = False

            value = click.prompt(field.name, type=field.type, default=default)

            if value != '': # Makes models fall back to defaults for this field
                setattr(instance, field.name, value) # TODO type enforcement

    instance.save(force_insert=True)


@app.cli.command()
@argument('storable', type=types.STORABLE)
@fake_before_request
def list(storable):

    for instance in storable.select():

        print "%s: %s - %s" % (instance.handle_string, instance.title, instance)


@app.cli.command()
@argument('storable', type=types.STORABLE)
@fake_before_request
def delete(storable):

    instance = click.prompt("%s handle" % storable.__name__, type=types.StorableInstanceParamType(storable))
    echo(instance)
    if confirm("Really delete this %s?" % storable.__name__):

        handle = instance.handle_string

        if instance.delete_instance(recursive=True):
            echo("Deleted %s %s" % (storable.__name__, handle))

        else:
            echo("Could not delete %s %s." % (storable.__name__, handle))


@app.cli.command()
def cron():

    app.cron_run()


@app.cli.command(name='import')
@argument('storable', type=types.STORABLE)
@argument('filepath', type=types.Path(exists=True))
@option('--skip-pk', type=types.BOOL, default=False, is_flag=True)
def import_(storable, filepath, skip_pk):

    fields = storable._meta.sorted_fields
    data = poobrains.helpers.ASVReader(filepath)

    with click.progressbar(data, label="Importing as %s" % storable.__name__, item_show_func=lambda x: x.values()[0] if x else '') as data_proxy: 

        for record in data_proxy:

            instance = storable()

            for field in fields:
                
                if isinstance(field, poobrains.storage.fields.AutoField):

                    if not skip_pk:
                        setattr(instance, field.name, int(record[field.name]))

                elif isinstance(field, poobrains.storage.fields.ForeignKeyField):

                    actual_name = "%s_id" % field.name

                    if record[actual_name] == u'':
                        setattr(instance, field.name, None)
                    else:
                        setattr(instance, field.name, field.rel_model.select().where(field.rel_model.id == record[actual_name])[0])

                else:

                    if record.has_key(field.name): # only fill fields for which we actually have values

                        if field.null and record[field.name] == u'':
                            setattr(instance, field.name, None) # insert NULL for empty strings if allowed, cleaner than just spamming the db with empty strings
                        else:
                            setattr(instance, field.name, field.type.convert(record[field.name], None, None))

            instance.save(force_insert=True)

    echo("Complete!")


@app.cli.command()
@argument('storable', type=types.STORABLE)
@argument('filepath', type=types.Path(exists=False))
@option('--skip-pk', type=types.BOOL, default=False, is_flag=True)
def export(storable, filepath, skip_pk):

    fields = storable._meta.sorted_fields
    writer = poobrains.helpers.ASVWriter(filepath)

    header = []
    for field in fields:

        value = field.name
        if isinstance(field, poobrains.storage.fields.ForeignKeyField):
            value += '_id' # TODO: Find out if this can ever not be '_id'

        header.append(value)


    writer.write_record(header) # write the header which is used to identify fields in imports

    with click.progressbar(storable.select(), label="Exporting", item_show_func=lambda x: x.title if x else '') as data_proxy: 
        for instance in data_proxy:

            record = []
            for field in fields:
                
                value = getattr(instance, field.name)
                    
                if value is None:
                    value = ''

                elif isinstance(field, poobrains.storage.fields.ForeignKeyField):
                    value = value._pk

                record.append(unicode(value))

            writer.write_record(record)

    echo("Complete!")


@app.cli.command()
@argument('datasets', type=types.StorableInstanceParamType(poobrains.svg.Dataset), nargs=-1)
@option('--file', type=types.Path(writable=True), default='plot.svg')
@fake_before_request
def plot(datasets, file):

    echo(u"Plotting…")
    plot = poobrains.svg.Plot(datasets=datasets)

    fd = codecs.open(file, 'w', encoding='utf-8')
    fd.write(plot.render('raw'))
    echo("Saved plot to %s!" % file)


@app.cli.command()
@argument('datasets', type=types.StorableInstanceParamType(poobrains.svg.MapDataset), nargs=-1)
@option('--file', type=types.Path(writable=True), default='map.svg')
@fake_before_request
def map(datasets, file):

    echo(u"Plotting…")
    map = poobrains.svg.Map(datasets=datasets)

    fd = codecs.open(file, 'w', encoding='utf-8')
    fd.write(map.render('raw'))
    echo("Saved map to %s!" % file)
