from sys import exit, stdout
from playhouse.db_url import connect
import helpers
import storage
import defaults

try:
    import config

except ImportError:
    config = False


class ShellException(Exception):
    pass


class NoSuchCommand(ShellException):
    pass


class InvalidValue(ShellException):
    pass


class TooManyParams(ShellException):
    pass


class MissingParam(ShellException):
    pass


def get_storables():
    
    storables = {}
    children = storage.Storable.children()
    for child in children:
        storables[child.__name__.lower()] = child

    return storables


def coerce_int(value):

    try:
        return int(value)
    except (ValueError, TypeError):
        raise InvalidValue("Invalid value for integer: '%s'." % (value,))


def coerce_str(value):

    if value is None:
        raise InvalidValue("String may not be empty.")

    try:
        return str(value)
    except (ValueError, TypeError):
        raise InvalidValue("Invalid value for string: '%s'." % (value,))


def coerce_storable(value):

    value = coerce_str(value)
    if not value in get_storables().keys():
        raise InvalidValue("Not a known storable: %s.", value)

    return value


def coerce_optional(value):

    if not value in (None, ''):
        raise InvalidValue("%s isn't a certified nothing." % (value,))

    return None




class Shell(object):

    prompt = "> "
    config = None
    commands = None


    def __init__(self):

        self.config = {}
        
        if config:
            for name in dir(config):
                if name.isupper():
                    self.config[name] = getattr(config, name)

        for name in dir(defaults):
            if name.isupper and not self.config.has_key(name):
                self.config[name] = getattr(defaults, name)

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
            stdout.write("No such command.")

        else:
            command = self.commands[command_name]()

            for param_name, coercions in command.params.iteritems():

                if len(unclean_params) > 0:
                    unclean_value = unclean_params.pop(0)
                else:

                    if  (isinstance(coercions, (tuple, list)) and coerce_optional not in coercions) ^ (coercions is not coerce_optional):
                            raise MissingParam('No value for %s.' % (param_name,))
                    unclean_value = None

                command.bind_param(param_name, unclean_value)

            return command



class Command(helpers.ChildAware):

    params = {'foo': coerce_int, 'bar': (coerce_int, None)} # Override this in subclasses for coercion
    values = None

    def __init__(self, **params):
        
        self.values = {}

        for param_name, value in params.iteritems():

            if param_name in self.params.keys():
                self.bind_param(param_name, value)



    def bind_param(self, param_name, value):

        if param_name in self.params:

            coercions = self.params[param_name]

            if not isinstance(coercions, (tuple, list)):
                coercions = (coercions,)

            for idx in range(0, len(coercions)):

                coercion = coercions[idx]

                if coercion is None:
                    coerced = value
                    break

                else:
                    try:
                        coerced = coercion(value)
                        break

                    except InvalidValue as e:
                        if idx == len(coercions) - 1:
                        #    raise InvalidValue("Parameter '%s' needs to conform to %s." % (param_name, "or ".join([str(c.__name__) for c in coercions])))
                            raise

            self.values[param_name] = coerced




    def execute(self):

        raise NotImplementedError("'%s' needs to implement its own 'execute' function." % (self.__class__.__name__,))


class Test(Command):

    params = {'count': (coerce_int, coerce_optional)}

    def execute(self):

        stdout.write("Running test command.\n")
        count = self.values['count'] or 10
        for i in range(1, count+1):
            stdout.write("%d\n" % (i,))


class IsInt(Command):

    params = {'test': coerce_int}

    def execute(self):

        stdout.write(self.values['test'])


class Exit(Command):

    params = {}

    def execute(self):

        exit(0)



class Help(Command):

    params = {}

    def execute(self):

        stdout.write("Commands: \n\n")
        
        for cls in Command.children():
            stdout.write("%s %s\n" % (cls.__name__.lower(), cls.params))

        stdout.write("\n")


class List(Command):

    params = {'storable': coerce_storable}

    def execute(self):

        storables = get_storables()

        storable = storables[self.values['storable']]
        for instance in storable.select():
            print "[%d][%s] %s" % (instance.id, instance.name, instance.title)

