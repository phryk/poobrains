# -*- coding: utf-8 -*-

import random
import functools
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
    
    for k,v in d.iteritems():

        if v['primary']:
           return v

    return d.values()[0]


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

        if kwargs.has_key('mode'):
            mode = kwargs['mode']
        else:
            #mode = content._meta.modes.keys()[0] # TODO: Default mode option in _meta?
            mode = None # will use default value for kwarg in .view

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
    _additional_keys = None # Why did I put this in, again? something something peewee compatibility…

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
            if attrs.has_key('Meta'):
                
                for option_name in recognized_options:
                    if hasattr(attrs['Meta'], option_name):
                        setattr(cls._meta, option_name, getattr(attrs['Meta'], option_name))
                    elif defaults.has_key(option_name):
                        setattr(cls._meta, option_name, defaults[option_name])

                delattr(cls, 'Meta')

            else:
                for option_name, default in defaults.iteritems():
                    setattr(cls._meta, option_name, default)

        else:
            cls._meta._additional_keys = cls._meta._additional_keys - set(['abstract']) # This makes the "abstract" property non-inheritable. FIXME: too hacky

            if not hasattr(cls._meta, 'abstract'):
                cls._meta.abstract = False

            if not hasattr(cls._meta, 'handle_fields'):
                cls._meta.handle_fields = [field.name for field in cls._meta.get_primary_key_fields()]

        return cls


class ChildAware(object):

    __metaclass__ = MetaCompatibility

    @classmethod
    def children(cls, abstract=False):

        reported_children = []
        children = cls.__subclasses__()

        for child in children:

            if abstract or not hasattr(child._meta, 'abstract') or not child._meta.abstract:
                reported_children.append(child)

            reported_children += child.children()

        return reported_children


    @classmethod
    def children_keyed(cls):

        children_keyed = OrderedDict()

        for child in cls.children():
            children_keyed[child.__name__] = child

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
                for lvl, ancestors in base.ancestors(_level+1).iteritems():

                    if not tiered.has_key(lvl):
                        tiered[lvl] = []
                    tiered[lvl] += ancestors

        if _level > 0:
            return tiered

        r = []
        for ancestors in tiered.itervalues():
            r += ancestors

        return r


class TrueDict(OrderedDict):

    def __setitem__(self, key, value):

        if value == True and True in self.itervalues() and self[name] != True:
            raise ValueError('Only one item may be True.')

        return super(TrueDict, self).__setitem__(key, value)


    def choose(self):

        if True in self.values():
            for choice, primary in self.iteritems():
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

        for k, v in self.iteritems():
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


    def iteritems(self):

        for key in self.keys():
            yield key, self[key]


    def itervalues(self):

        for key in self.keys():
            yield self[key]


    def clear(self):
        super(CustomOrderedDict, self).clear()
        self.order = []


    def keys(self):
        return self.order
