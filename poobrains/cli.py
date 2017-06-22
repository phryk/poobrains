# -*- coding: utf-8 -*-

from sys import exit, stdout
from playhouse.db_url import connect
import collections
import peewee
import helpers
import gnupg

# local imports
import storage
import auth

import poobrains

class ShellException(Exception):
    pass


class NoSuchCommand(ShellException):
    pass


class NoSuchParameter(ShellException):
    pass


class InvalidValue(ShellException):
    pass


class TooManyParams(ShellException):
    pass


class MissingParameter(ShellException):
    pass



class Shell(object):

    prompt = "> "
    config = None
    commands = None


    def __init__(self, config):

        super(Shell, self).__init__()
        self.config = config

        #for child in storage.Storable.children():
        #    self.storables[child.__name__.lower()] = child
        
        self.db = connect(self.config['DATABASE'], autocommit=True, autorollback=True)

        self.commands = {}
        classes = Command.class_children()

        for cls in classes:
            self.commands[cls.__name__.lower()] = cls


    def start(self):
        
        while True:

            try:
                self.db.connect()
                command = self.get_command()

                try:
                    command.execute()

                except Exception as e:
                    stdout.write("Failed executing: %s\n\n" % (e,))
                    if self.config['DEBUG']:
                        raise

            except NoSuchCommand as e:

                stdout.write("No such command: %s\n\n" % (e,))

            except NoSuchParameter as e:

                stdout.write("Missing parameter: %s\n" % (e,))
                try:
                    comand_help = Help(command=command.__class__.__name__.lower())
                except Exception:
                    pass
                else:
                    stdout.write("%s\n" % (command_help.execute(),))

            except ShellException as e:

                stdout.write("An error occured: %s\n\n" % (e,))

            finally:
                if not self.db.is_closed():
                    self.db.close()


    def get_command(self):

        stdout.write(self.prompt)
        line = raw_input()
        
        unclean_params = line.split(' ')
        command_name =  unclean_params.pop(0)

        if not self.commands.has_key(command_name):
            raise NoSuchCommand(command_name)

        else:
            command = self.commands[command_name](self)

            for param_name, parameter in command.parameters.iteritems():

                if len(unclean_params) > 0:
                    unclean_value = unclean_params.pop(0)
                else:
                    unclean_value = None # we're dealing with an optional parameter that hasn't been passed

                command.bind_param(param_name, unclean_value)

            return command



# Parameter classes below this

class Parameter(object):

    type = None
    optional = None
    command = None

    def __init__(self, optional=False):

        super(Parameter, self).__init__()
        self.optional = optional


    def bind(self, command):
        self.command = command


    def parse(self, value):

        raise NotImplementedError("Parameter class %s does not implement parse." % self.__class__.__name__)


class IntParam(Parameter):

    def parse(self, value):

        if self.optional and value is None:
            return None

        try:
            return int(value)
        except (ValueError, TypeError):
            raise InvalidValue("Invalid value for integer: %s." % (value,))


class StringParam(Parameter):

    def parse(self, value):

        if self.optional and value is None:
            return None

        if value is None:
            raise InvalidValue("String may not be empty.")

        try:
            return str(value)
        except (ValueError, TypeError):
            raise InvalidValue("Invalid value for string: '%s'." % (value,))


# Command classes

class Command(helpers.ChildAware):

    #params = {'foo': coerce_int, 'bar': (coerce_int, None)} # Override this in subclasses for coercion
    shell = None
    parameters = None
    values = None

    class Meta:
        abstract = True
    
    @classmethod
    def get_parameters(cls):

        parameters = collections.OrderedDict()
        for attr_name in dir(cls):

            attr = getattr(cls, attr_name)
            if isinstance(attr, Parameter):
                parameters[attr_name] = attr

        return parameters


    def __init__(self, shell, **params):

        self.shell = shell
        self.parameters = self.__class__.get_parameters()

        self.values = {}
        for param_name, value in params.iteritems():

            if param_name in self.params.keys():
                self.bind_param(param_name, value)


    def bind_param(self, param_name, value):

        if not param_name in self.parameters.keys():

            raise NoSuchParameter(param_name)

        parameter = self.parameters[param_name]
        parameter.bind(self)
        coerced = parameter.parse(value)
        self.values[param_name] = coerced

    
    def execute(self):

        raise NotImplementedError("'%s' needs to implement its own 'execute' function." % (self.__class__.__name__,))


class Test(Command):

    #params = {'count': (coerce_int, coerce_optional)}
    count = IntParam(optional=True)

    def execute(self):

        stdout.write("Running test command.\n")
        count = self.values['count'] or 10
        for i in range(1, count+1):
            stdout.write("%d\n" % (i,))


class Install(Command):

    def execute(self):

        stdout.write("Really execute installation procedure? (y/N): ")
        value = raw_input().lower()
        if value == 'y':

            config_addendum = collections.OrderedDict()

            stdout.write("Installing now...\n")

            self.shell.db.create_tables(poobrains.storage.Model.class_children())
            stdout.write("Database tables created!\n")


            stdout.write("Creating Group 'anonsanonymous'…\n")
            anons = poobrains.auth.Group()
            anons.name = 'anonsanonymous'
            
            if not anons.save(force_insert=True):
                raise ShellException("Failed creating Group 'anonsanonymous'!")
            stdout.write("Successfully created Group 'anonsanonymous'.\n")


            stdout.write("Creating Group 'administrators' with all permissions granted…\n")
            admins = poobrains.auth.Group()
            admins.name = 'administrators'
            
            for cls in poobrains.auth.Permission.class_children():
                choice_values = [x[0] for x in cls.choices]
                if 'grant' in choice_values:
                    access = 'grant'
                else:
                    stdout.write("Don't know what access value to use for permission '%s', skipping.\n" % cls.__name__)
                    break

                stdout.write("Adding permission %s: %s\n" % (cls.__name__, access))
                admins.own_permissions[cls.__name__] = access
            
            if not admins.save(force_insert=True):
                raise ShellException("Failed creating Group 'administrators'!")

            stdout.write("Successfully saved Group 'administrators'.\n")


            anon = poobrains.auth.User()
            anon.name = 'anonymous'
            #anon.id = 1 # Should theoretically always happen, but let's make sure anyways; This fucks up postgresql's stupid SERIAL sequence thing
            anon.groups.append(anons)
            if not anon.save(force_insert=True):
                raise ShellException("Failed creating User 'anonymous'!")
            stdout.write("Successfully created User 'anonymous'.\n")
            stdout.write(str(anon))

            stdout.write("Administrator email addr: ")
            admin_mail = raw_input()
            stdout.write("Creating administrator account…\n")
            admin = poobrains.auth.User()
            admin.name = 'administrator'
            admin.mail = admin_mail
            admin.groups.append(admins) # Put 'administrator' into group 'administrators'

            if not admin.save():
                
                raise ShellException("Couldn't save administrator, please try again or fix according bugs.")

            stdout.write("Successfully saved administrator account.\n")
            stdout.write("Please type in a name for an admin certificate: ")
            cert_name = raw_input()

            t = poobrains.auth.ClientCertToken()
            t.user = admin
            t.cert_name = cert_name

            if t.save():
                stdout.write("Admin certificate token is: %s\n" % t.token)

            stdout.write("SMTP host: ")
            config_addendum['SMTP_HOST'] = raw_input()
            
            stdout.write("SMTP port: ")
            config_addendum['SMTP_PORT'] = raw_input()
            
            stdout.write("SMTP account: ")
            config_addendum['SMTP_ACCOUNT'] = raw_input()
            
            stdout.write("SMTP password: ")
            config_addendum['SMTP_PASSWORD'] = raw_input()

            stdout.write("SMTP from: ")
            site_mail = raw_input()
            config_addendum['SMTP_FROM'] = site_mail
            
            stdout.write("We'll now configure GPG for sending encrypted mail.\n")
            stdout.write("GPG home (relative to project root): ")
            gpg_home = raw_input()

            gpg = gnupg.GPG(binary=poobrains.app.config['GPG_BINARY'], homedir=gpg_home)
            config_addendum['GPG_HOME'] = gpg_home
            
            stdout.write("Site PGP passphrase :")
            passphrase = raw_input()
            config_addendum['GPG_PASSPHRASE'] = passphrase


            stdout.write("Creating trustdb, if it doesn't exist\n")
            gpg.create_trustdb()
            site_gpg_info = gpg.gen_key_input(
                name_email = site_mail,
                key_type = 'RSA',
                key_length = 4096,
                key_usage = 'encrypt,sign',
                passphrase = passphrase
            )

            stdout.write("Generating PGP key for this site. This will probably take a pretty long while. Go get a sammich.\n")
            gpg.gen_key(site_gpg_info)
            
            stdout.write("Probably created site PGP key")


            stdout.write("Installation complete!\n")

            stdout.write("Add these lines to your config.py:\n\n")

            for k, v in config_addendum.iteritems():
                stdout.write("%s = %s\n" % (k, v))


class Exit(Command):

    def execute(self):

        exit(0)


class Help(Command):

    commands = None
    command = StringParam(optional=True)

    def __init__(self, shell, **params):

        super(Help, self).__init__(shell, **params)

        self.commands = collections.OrderedDict()
        classes = Command.class_children()

        for cls in classes:
            self.commands[cls.__name__.lower()] = cls


    def execute(self):

        if self.values['command']:

            if not self.commands.has_key(self.values['command']):
                raise NoSuchCommand(self.values['command'])

            stdout.write("%s\n" % (self.command_help(self.values['command']),))
            return

        stdout.write("Commands: \n\n")

        for command_name in self.commands.keys():
            stdout.write("%s\n" % (self.command_help(command_name),))

        stdout.write("\n")


    def command_help(self, command_name):

        cls = self.commands[command_name]
        params = cls.get_parameters()

        param_descs = []
        for name, param in params.iteritems():

            param_desc = "%s (%s)" % (name, param.__class__.__name__)

            if param.optional:
                param_desc = "[%s]" % (param_desc,)

            else:
                param_desc = "<%s>" % (param_desc,)

            param_descs.append(param_desc)

        return "%s %s" % (command_name, ', '.join(param_descs))



class StorableParam(StringParam):

    """
    String parameter which only validates successfully if the value is the name of a storable class.
    'cls' param to constructor limits valid values to children of that class.
    """

    cls = None

    def __init__(self, *args, **kw):

        if kw.has_key('cls'):
            self.cls = cls
        else:
            self.cls = poobrains.storage.Storable

    def parse(self, value):

        accepted_storables = collections.OrderedDict([(k.lower(), v) for k, v in self.cls.class_children_keyed().iteritems()])

        if self.optional and value is None:
            return None

        if not isinstance(value, basestring):
            raise InvalidValue("No storable supplied. Take one of these: %s" % (', '.join(accepted_storables.keys())))
        elif not (value.lower() in accepted_storables.keys()):
            raise InvalidValue("Not a known storable: %s. Take one of these: %s" % (value, ', '.join(accepted_storables.keys())))

        return accepted_storables[value]


class List(Command):

    storable = StorableParam()

    def execute(self):

        storable = self.values['storable']
        for instance in storable.select():
            print "[%d][%s] %s" % (instance.id, instance.name, instance.__repr__())


class Add(Command):

    #FIXME: This doesn't work for Storables with CompositeKey as primary key.
    #params = {'storable': coerce_storable, 'handle': 'coerce_string'}
    storable = StorableParam()

    def execute(self):
        
        cls = self.values['storable']
        instance = cls()

        stdout.write("Addding %s...\n" % (cls.__name__,))
        for field in cls._meta.sorted_fields:

            if not isinstance(field, peewee.PrimaryKeyField):
                stdout.write("%s: " % (field.name,))
                value = raw_input()

                if value != '': # Makes models fall back to defaults for this field
                    setattr(instance, field.name, value) # TODO type enforcement

        instance.save(force_insert=True)
