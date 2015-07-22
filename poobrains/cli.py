from sys import exit, stdout
from playhouse.db_url import connect
from collections import OrderedDict
import peewee
import helpers
import storage




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

        self.config = config

        self.storables = {}
        for child in storage.Storable.children():
            self.storables[child.__name__.lower()] = child
        
        self.db = connect(self.config['DATABASE'])
        storage.proxy.initialize(self.db)

        self.commands = {}
        classes = Command.children()

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

        self.optional = optional


    def bind(self, command):
        self.command = command


    def parse(self, value):

        raise NotImplementedError("Fuck you.")


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


class StorableParam(StringParam):

    def parse(self, value):

        if self.optional and value is None:
            return None

        if not value in self.command.storables.keys():
            raise InvalidValue("Not a known storable: %s. Take one of these: %s" % (value, ', '.join(self.command.storables.keys())))

        return value



# Command classes

class Command(helpers.ChildAware):

    #params = {'foo': coerce_int, 'bar': (coerce_int, None)} # Override this in subclasses for coercion
    shell = None
    storables = None
    parameters = None
    values = None

    
    @classmethod
    def get_parameters(cls):

        parameters = OrderedDict()
        for attr_name in dir(cls):

            attr = getattr(cls, attr_name)
            if isinstance(attr, Parameter):
                parameters[attr_name] = attr

        return parameters


    def __init__(self, shell, **params):

        self.shell = shell
        self.storables = self.shell.storables
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


class Exit(Command):

    #params = {}

    def execute(self):

        exit(0)


class Help(Command):

    commands = None
    command = StringParam(optional=True)

    def __init__(self, shell, **params):

        super(Help, self).__init__(shell, **params)

        self.commands = OrderedDict()
        classes = Command.children()

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



class List(Command):

    #params = {'storable': coerce_storable}
    storable = StorableParam()

    def execute(self):

        storable = self.storables[self.values['storable']]
        for instance in storable.select():
            print "[%d][%s] %s" % (instance.id, instance.name, instance.title)


class Add(Command):

    #params = {'storable': coerce_storable, 'id_or_name': 'coerce_string'}
    storable = StorableParam()

    def execute(self):
        
        if self.storables.has_key(self.values['storable']):

            cls = self.storables[self.values['storable']]
            instance = cls()

            stdout.write("Addding %s...\n" % (cls.__name__,))
            for field in cls._meta.get_fields():

                if not isinstance(field, peewee.PrimaryKeyField):
                    stdout.write("%s: " % (field.name,))
                    value = raw_input()

                    setattr(instance, field.name, value) # TODO type enforcement

            instance.save()
