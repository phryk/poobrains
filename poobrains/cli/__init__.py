# -*- coding: utf-8 -*-

import collections
import os
import peewee
import gnupg
import flask
import click
import jinja2

from playhouse import db_url

#import poobrains
from poobrains import app
import poobrains.helpers
import poobrains.storage
import poobrains.auth

import __main__ # to look up project name

project_name = os.path.splitext(os.path.basename(__main__.__file__))[0] # basically filename of called file - extension


def mkconfig(template, **values):

    template_dir = os.path.join(app.poobrain_path, 'cli', 'templates')
    jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))
    template = jinja_env.get_template('%s.jinja' % template)

    return template.render(**values)


@app.cli.command()
def test():
    click.echo("Running test command!")


@app.cli.command()
@click.option('--domain', prompt="Domain this site will be run under?", default="localhost")
@click.option('--database', prompt="Database url", default="sqlite:///%s.db" % project_name)
@click.option('--deployment', prompt="Please choose your way of deployment for automatic config generation", type=click.Choice(['uwsgi+nginx', 'custom']), default='uwsgi+nginx')
@click.option('--deployment-os', prompt="What OS are you deploying to?", type=click.Choice(['linux', 'freebsd']), default=lambda: os.uname()[0].lower())
@click.option('--mail-address', prompt="Site email address") # FIXME: needs a regexp check
@click.option('--mail-server', prompt="Site email server") # FIXME: needs regexp check, maybe connection check
@click.option('--mail-port', prompt="Site email server port", type=int)
@click.option('--mail-user', prompt="Site email account username")
@click.option('--mail-password', prompt="Site email password")
@click.option('--admin-mail-address', prompt="Admin email address") # FIXME: needs a regexp check
@click.option('--admin-cert-name', prompt="Admin login certificate name", default="%s-initial" % app.config['SITE_NAME']) # FIXME: needs a regexp check
@click.option('--gnupg-homedir', prompt="gnupg homedir, relative to project root (corresponds to gpgs' --homedir)", default="gnupg")
@click.option('--gnupg-passphrase', prompt="gnupg passphrase (used to create a keypair)", default=lambda: poobrains.helpers.random_string_light(64))
def install(**options):

        value = click.prompt("Really execute installation procedure? (y/N)").lower()
        if value == 'y':

            options['project_name'] = project_name
            options['project_dir'] = app.site_path
            options['secret_key'] = poobrains.helpers.random_string_light(64) # cookie crypto key, config['SECRET_KEY']

            #config_addendum = collections.OrderedDict()

            app.db = db_url.connect(options['database'], autocommit=True, autorollback=True)
            click.echo("Installing now...\n")

            app.db.create_tables(poobrains.storage.Model.class_children())
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

                click.echo("Adding permission %s: %s\n" % (cls.__name__, access))
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

            #config_addendum['SMTP_HOST'] = click.prompt("SMTP host")
            #config_addendum['SMTP_PORT'] = click.prompt("SMTP port")
            #config_addendum['SMTP_ACCOUNT'] = click.prompt("SMTP account")
            #config_addendum['SMTP_PASSWORD'] = click.prompt("SMTP password")

            #site_mail = click.prompt("SMTP from")
            #config_addendum['SMTP_FROM'] = site_mail
            
            click.echo("We'll now configure GPG for sending encrypted mail.\n")
            #gpg_home = click.prompt("GPG home (relative to project root)")

            gpg = gnupg.GPG(binary=app.config['GPG_BINARY'], homedir=options['gnupg_homedir'])
            #config_addendum['GPG_HOME'] = gpg_home
            
            #config_addendum['GPG_PASSPHRASE'] = passphrase


            click.echo("Creating trustdb, if it doesn't exist\n")
            gpg.create_trustdb()
            site_gpg_info = gpg.gen_key_input(
                name_email = options['mail_address'],
                key_type = 'RSA',
                key_length = 4096,
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
@click.argument('storable')
def add(storable):

        cls = poobrains.storage.Storable.class_children_keyed()[storable]
        instance = cls()

        click.echo("Addding %s...\n" % (cls.__name__,))
        for field in cls._meta.sorted_fields:

            if not isinstance(field, peewee.PrimaryKeyField):
                value = click.prompt(field.name)

                if value != '': # Makes models fall back to defaults for this field
                    setattr(instance, field.name, value) # TODO type enforcement

        instance.save(force_insert=True)

@app.cli.command()
def cron():

    app.cron_run()
