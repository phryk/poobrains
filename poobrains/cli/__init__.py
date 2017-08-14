# -*- coding: utf-8 -*-

import collections
import peewee
import gnupg
import flask
import click

import os.path

#import poobrains
from poobrains import app
import poobrains.storage
import poobrains.auth

def mkconfig(template, **values):

    app.debugger.set_trace()
    template_path = os.path.join(app.poobrain_path, 'cli', 'templates', template)
    return flask.render_template(template_path, **values)


@app.cli.command()
def test():
    click.echo("Running test command!")
    print mkconfig('uwsgi_freebsd.ini', project_dir="/foo/bar", project_name="bar")

@app.cli.command()
def install():

        value = click.prompt("Really execute installation procedure? (y/N)").lower()
        if value == 'y':

            config_addendum = collections.OrderedDict()

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
            click.echo(str(anon))

            admin_mail = click.prompt("Administrator email addr")
            click.echo("Creating administrator account…\n")
            admin = poobrains.auth.User()
            admin.name = 'administrator'
            admin.mail = admin_mail
            admin.groups.append(admins) # Put 'administrator' into group 'administrators'

            if not admin.save():
                
                raise ShellException("Couldn't save administrator, please try again or fix according bugs.")

            click.echo("Successfully saved administrator account.\n")
            cert_name = click.prompt("Please type in a name for an admin certificate")

            t = poobrains.auth.ClientCertToken()
            t.user = admin
            t.cert_name = cert_name

            if t.save():
                click.echo("Admin certificate token is: %s\n" % t.token)

            config_addendum['SMTP_HOST'] = click.prompt("SMTP host")
            
            config_addendum['SMTP_PORT'] = click.prompt("SMTP port")
            
            config_addendum['SMTP_ACCOUNT'] = click.prompt("SMTP account")
            
            config_addendum['SMTP_PASSWORD'] = click.prompt("SMTP password")

            site_mail = click.prompt("SMTP from")
            config_addendum['SMTP_FROM'] = site_mail
            
            click.echo("We'll now configure GPG for sending encrypted mail.\n")
            gpg_home = click.prompt("GPG home (relative to project root)")

            gpg = gnupg.GPG(binary=app.config['GPG_BINARY'], homedir=gpg_home)
            config_addendum['GPG_HOME'] = gpg_home
            
            passphrase = click.prompt("Site PGP passphrase")
            config_addendum['GPG_PASSPHRASE'] = passphrase


            click.echo("Creating trustdb, if it doesn't exist\n")
            gpg.create_trustdb()
            site_gpg_info = gpg.gen_key_input(
                name_email = site_mail,
                key_type = 'RSA',
                key_length = 4096,
                key_usage = 'encrypt,sign',
                passphrase = passphrase
            )

            click.echo("Generating PGP key for this site. This will probably take a pretty long while. Go get a sammich.\n")
            gpg.gen_key(site_gpg_info)
            
            click.echo("Probably created site PGP key")


            click.echo("Installation complete!\n")

            click.echo("Add these lines to your config.py:\n\n")

            for k, v in config_addendum.iteritems():
                click.echo("%s = %s\n" % (k, v))


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
