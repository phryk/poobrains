# -*- coding: utf-8 -*-

import string
import random
import functools
import codecs # so we can open a file as utf-8 in order to parse ASV for importing data
import werkzeug
import peewee
import flask

from collections import OrderedDict


def random_string(length=42):

    rand = random.SystemRandom() # uses os.urandom, which is supposed to be cryptographically secure
    string = u''
    for i in range(0, length):
        string += chr(rand.randint(33, 126)) # printable ascii chars are chars 33 - 126 #TODO: Should I even bother finding out whether unicode is an option?

    return string


def random_string_light(length=8):

    ranges = ((65, 90), (97, 122)) # A-Z, a-z
    rand = random.SystemRandom()
    string = u''

    for i in range(0, length):
        r = ranges[rand.randint(0, len(ranges)-1)]
        string += chr(rand.randint(r[0], r[1]))

    return string


def flatten_nested_multidict(v):

    flat = []

    if not isinstance(v, werkzeug.datastructures.MultiDict):
        flat.append(v)
    else:
        for _, value in werkzeug.datastructures.iter_multi_items(v):
            flat += flatten_nested_multidict(value)

    return flat


def choose_primary(d):
    
    for k,v in d.items():

        if v['primary']:
           return v

    return d.values()[0]


def clean_string(s):
    
    allowed_chars = string.ascii_lowercase + string.digits + '-'
    clean = ""

    #if not isinstance(s, unicode):
    #    s = unicode(s.decode('utf-8'))

    s = s.lower()

    substitutions = {
        u'ä': u'ae',
        u' ': u'-',
        u'ö': u'oe',
        u'ü': u'ue',
        u'ß': u'ss'
    }

    for pattern, substitute in substitutions.items():
        s = s.replace(pattern, substitute)

    for char in s:
        if char in allowed_chars:
            clean += char

    return clean


def themed(f):

    @functools.wraps(f)
    def real(*args, **kwargs):
        
        rv = f(*args, **kwargs)

        if isinstance(rv, tuple):
            content = rv[0]
            status_code = rv[1]

        else:
            content = rv
            status_code = 200 # TODO: Find out if this is too naive


        if isinstance(content, werkzeug.wrappers.Response):
            return rv # pass Responses (i.e. redirects) upwards

        elif isinstance(content, ThemedPassthrough):
            return rv.themed


        if hasattr(content, '_title') and content._title:
            flask.g.title = content._title

        elif hasattr(content, 'title') and content.title:
            flask.g.title = content.title

        elif hasattr(content, 'name') and content.name:
            flask.g.title = content.name

        else:
            flask.g.title = content.__class__.__name__
        flask.g.content = content

        if hasattr(flask.g, 'user'):
            user = flask.g.user
        else:
            user = None

        if 'mode' in kwargs:
            mode = kwargs['mode']
        else:
            #mode = content._meta.modes.keys()[0] # TODO: Default mode option in _meta?
            mode = 'full' # will use default value for kwarg in .view

        return flask.render_template('main.jinja', content=content, mode=mode, user=user), status_code

    return real



def is_secure(f):

    """
    decorator. Denies access if an url is accessed without TLS.
    """

    @functools.wraps(f)
    def substitute(*args, **kwargs):

        if flask.request.is_secure:
            return f(*args, **kwargs)

        else:
            flask.abort(403, "You are trying to do naughty things without protection.")

    return substitute


def pretty_bytes(bytecount):

    """
    Return a human readable representation given a size in bytes.
    """

    units = ['Byte', 'Kilobyte', 'Megabyte', 'Gigabyte', 'Terabyte']

    value = bytecount
    for unit in units:
        if value / 1024.0 < 1:
            break

        value /= 1024.0

    return "%.2f %s" % (value, unit)


class ThemedPassthrough(object):

    themed = None

    def __init__(self, themed):
        self.themed = themed


class ClassOrInstanceBound(type): # probably the worst name I ever picked, but hey it's descriptive! ¯\_(ツ)_/¯

    def __get__(self, instance, owner):

        if instance:
            return functools.partial(self, instance)
        return functools.partial(self, owner)
        # TODO: return functools.partial(self, instance or owner)


class FakeMetaOptions(object):

    primary_key = None # This is a very ugly hack, to make this play nice with peewee Metaclass' __new__
    abstract = None
    handle_fields = None
    modes = None
    permission_class = None
    schema = None  # needed by peewee.ModelBase.__new__
    _additional_keys = None # needed by peewee.ModelBase.__new__

    def __init__(self):

        super(FakeMetaOptions, self).__init__()
        self.abstract = False
        self._additional_keys = set([])


class MetaCompatibility(type):

    """
    Make a non-Model class compatible with peewees 'class Meta' pattern.
    This is a hack.
    """

    def __new__(cls, name, bases, attrs):

        recognized_options = ['abstract', 'modes', 'permission_class', 'handle_fields', 'clone_props'] # FIXME: Make this shit generic, like peewee ModelOptions

        cls = super(MetaCompatibility, cls).__new__(cls, name, bases, attrs)
 
        defaults = {}
        if hasattr(cls, '_meta'):
            for option_name in recognized_options:
                if hasattr(cls._meta, option_name):
                    defaults[option_name] = getattr(cls._meta, option_name)

        defaults['abstract'] = False

        if not issubclass(cls, peewee.Model): # Maybe suboptimal, but can't get poobrains.storage from here, I think

            cls._meta = FakeMetaOptions()

            #if hasattr(cls, 'Meta'):
            if 'Meta' in attrs:
                print(f"Meta for  {name}")
                for option_name in recognized_options:
                    if hasattr(attrs['Meta'], option_name):
                        setattr(cls._meta, option_name, getattr(attrs['Meta'], option_name))
                    elif option_name in defaults:
                        setattr(cls._meta, option_name, defaults[option_name])

                delattr(cls, 'Meta')

            else:
                for option_name, default in defaults.items():
                    setattr(cls._meta, option_name, default)

        else:
            cls._meta._additional_keys = cls._meta._additional_keys - set(['abstract']) # This makes the "abstract" property non-inheritable. FIXME: too hacky

            if not hasattr(cls._meta, 'abstract'):
                cls._meta.abstract = False

            if not hasattr(cls._meta, 'handle_fields'):
                cls._meta.handle_fields = [field.name for field in cls._meta.get_primary_keys()]

        return cls


class ChildAware(object, metaclass=MetaCompatibility):

    __metaclass__ = MetaCompatibility

    @classmethod
    def class_children(cls, abstract=False):

        reported_children = set()
        children = cls.__subclasses__()

        for child in children:

            if abstract or not hasattr(child._meta, 'abstract') or not child._meta.abstract:
                reported_children.add(child)

            reported_children = reported_children.union(child.class_children())

        return reported_children


    @classmethod
    def class_children_keyed(cls, lower=False):

        children_keyed = OrderedDict()

        for child in cls.class_children():
            key = child.__name__.lower() if lower else child.__name__
            children_keyed[key] = child

        return children_keyed


    @classmethod
    def ancestors(cls, _level=0):

        """
        Get the ancestors of this class, ordered by how far up the hierarchy they are.

        """

        tiered = OrderedDict()
        tiered[_level] = []

        for base in cls.__bases__:

            if base is ChildAware:
                break

            tiered[_level].append(base)
            if hasattr(base, 'ancestors'):
                for lvl, ancestors in base.ancestors(_level+1).items():

                    if not lvl in tiered:
                        tiered[lvl] = []
                    tiered[lvl] += ancestors

        if _level > 0:
            return tiered

        r = []
        for ancestors in tiered.values():
            r += ancestors

        return r


class TrueDict(OrderedDict):

    def __setitem__(self, key, value):

        if value == True and True in self.values() and self[name] != True:
            raise ValueError('Only one item may be True.')

        return super(TrueDict, self).__setitem__(key, value)


    def choose(self):

        if True in self.values():
            for choice, primary in self.items():
                if primary == True:
                    break
        else:
            choice = self.keys()[0]

        return choice


class CustomOrderedDict(dict):

    order = None

    def __init__(self, *args, **kw):
        self.order = []
        super(CustomOrderedDict, self).__init__(*args, **kw)


    def __repr__(self):

        repr = '{'

        for k, v in self.items():
            repr += '%s: %s' % (k.__repr__(), v.__repr__())

        repr += '}'
        return repr


    def __setitem__(self, key, value):

        super(CustomOrderedDict, self).__setitem__(key, value)
        if key not in self.keys(): # add key to order only if needed, leave position unchanged otherwise
            self.order.append(key)


    def __delitem__(self, key):
        super(CustomOrderedDict, self).__delitem__(key)
        self.order.remove(key)


    def __iter__(self):

        for key in self.keys():
            yield key


    def items(self):

        for key in self.keys():
            yield key, self[key]


    def values(self):

        for key in self.keys():
            yield self[key]


    def clear(self):
        super(CustomOrderedDict, self).clear()
        self.order = []


    def keys(self):
        return self.order


class ASVReader(object):

    filepath = None

    def __init__(self, filepath):

        super(ASVReader, self).__init__()
        self.filepath = filepath


    def __iter__(self):

        return ASVIterator(self)


class ASVIterator(object):

    asv = None
    fd = None

    def __init__(self, asv):

        self.asv = asv
        self.fd = codecs.open(self.asv.filepath, 'r', encoding='utf-8')
        self.keys = self.next_list()
    
    
    def __del__(self):
        self.fd.close()


    def next_list(self):

        """ Get the next record of the file as list """

        record = []
        current_token = u''

        while True:

            char = self.fd.read(1) # one unicode char, no matter how many bytes, compliments of the codecs module

            if len(char) == 0:
                raise StopIteration('ASV File was fully read.')

            elif char == chr(0x1F): # unit separator, means the current column was fully read
                record.append(current_token)
                current_token = u''

            elif char == chr(0x1E): # record separator, means we have reached the end of the line (or rather record)
                record.append(current_token)
                return record

            else:
                current_token += char


    def next(self):

        return OrderedDict(zip(self.keys, self.next_list()))


class ASVWriter(object):

    fd = None

    unit_separator = chr(0x1F)
    record_terminator = chr(0x1E)


    def __init__(self, filepath):

        self.fd = codecs.open(filepath, 'a', encoding='utf-8')

    def write_record(self, record):

        self.fd.write("%s%s" % (self.unit_separator.join(record), self.record_terminator))


    def __del__(self):
        self.fd.close()
