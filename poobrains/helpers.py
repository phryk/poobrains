# -*- coding: utf-8 -*-

import random
import functools
import werkzeug
import peewee
import flask

from collections import OrderedDict


def random_string(length=42):

    rand = random.SystemRandom()
    string = u''
    for i in range(0, length):
        string += chr(rand.randint(33, 126)) # printable ascii chars are chars 33 - 126 #TODO: Should I even bother finding out whether unicode is an option?

    return string


def choose_primary(d):
    
    for k,v in d.iteritems():

        if v['primary']:
           return v

    return d.values()[0]


def render(mode=None):

    def decorator(f):

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

            if hasattr(content, 'title') and content.title:
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
            return flask.render_template('main.jinja', content=content, mode=mode, user=user), status_code

        return real

    return decorator


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


def load_storable(cls):

    def decorator(func):

        @functools.wraps(func)
        def substitute(id_or_name=None, *args, **kwargs):
            if id_or_name:
                instance = cls.load(id_or_name)

            else: # should only happen for 'add' mode for storables, or any for forms
                instance = cls()

            return func(instance, *args, **kwargs)

        return substitute

    return decorator


def access(permission):

    def decorator(func):

        @functools.wraps(func)
        def substitute(*args, **kwargs):

            try:
                flask.g.user.access(permission)
            except errors.PermissionDenied as e:
                abort(403, 'Permission denied!') # TODO: Find out if this actually stops further execution of this function

            return func(*args, **kwargs)


class ClassOrInstanceBound(type): # probably the worst name I ever picked, but hey it's descriptive! ¯\_(ツ)_/¯

    def __get__(self, instance, owner):

        if instance:
            return functools.partial(self, instance)
        return functools.partial(self, owner)
        # TODO: return functools.partial(self, instance or owner)


class FakeMetaOptions(object):

    abstract = None
    modes = None
    permission_class = None
    _additional_keys = None

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
        
        #if name.startswith('Owned'):
            #import pudb; pudb.set_trace()

        cls = super(MetaCompatibility, cls).__new__(cls, name, bases, attrs)
        recognized_options = ['abstract', 'modes', 'permission_class']

        if issubclass(cls, peewee.Model): # Maybe suboptimal, but can't get poobrains.storage from here, I think
            print "jackpot: ", name
        else:
            print "nope: ", name


        if hasattr(cls, 'Meta'):

            if not hasattr(cls, '_meta'):
                cls._meta = FakeMetaOptions()

#            if hasattr(cls.Meta, 'abstract'):
#                cls._meta.abstract = cls.Meta.abstract
#
#            if hasattr(cls.Meta, 'modes'):
#                cls._meta.modes = cls.Meta.modes

            for option_name in recognized_options:
                if hasattr(cls.Meta, option_name):
                    setattr(cls._meta, option_name, getattr(cls.Meta, option_name))

            delattr(cls, 'Meta')

        elif hasattr(cls, '_meta'):
            if isinstance(cls._meta, FakeMetaOptions):

                if hasattr(cls._meta, 'abstract'):
                    cls._meta.abstract = False # TODO: Would delattr be "cleaner"?

            else:
                cls._meta._additional_keys = cls._meta._additional_keys - set(['abstract']) # This makes the "abstract" property non-inheritable. FIXME: too hacky

        else:
            cls._meta = FakeMetaOptions()

        return cls


class ChildAware(object):

    __metaclass__ = MetaCompatibility

    @classmethod
    def children(cls, abstract=False):

        reported_children = []
        children = cls.__subclasses__()

        for child in children:

            if abstract or not hasattr(child, '_meta') or not hasattr(child._meta, 'abstract') or not child._meta.abstract:
                reported_children.append(child)

            reported_children += child.children()

        return reported_children

    @classmethod
    def children_keyed(cls):

        children_keyed = OrderedDict()

        for child in cls.children():
            children_keyed[child.__name__.lower()] = child

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
