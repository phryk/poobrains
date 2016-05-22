# -*- coding: utf-8 -*-

import random
import functools
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

class FakeMetaOptions(object):

    abstract = None
    _additional_keys = None

    def __init__(self):

        self.abstract = False
        self._additional_keys = set([])


class MetaCompatibility(type):

    """
    Make a non-Model class compatible with peewees 'class Meta' pattern.
    This is a hack.
    """

    def __new__(cls, name, bases, attrs):

        cls = super(MetaCompatibility, cls).__new__(cls, name, bases, attrs)

        if hasattr(cls, 'Meta'):

            cls._meta = FakeMetaOptions()

            if hasattr(cls.Meta, 'abstract'):
                cls._meta.abstract = cls.Meta.abstract
            delattr(cls, 'Meta')

        elif hasattr(cls, '_meta'):
            if isinstance(cls._meta, FakeMetaOptions):
                cls._meta = FakeMetaOptions()
            else:
                cls._meta._additional_keys = cls._meta._additional_keys - set(['abstract']) # This makes the "abstract" property non-inheritable.

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
    def ancestors(cls, top=None):

        """
        params:
            * top: class, when this class is reached, the iteration is stopped
        """

        ancestors = []

        if top is None:
            top = ChildAware

        for base in cls.__bases__:

            ancestors.append(base)

            if base is top:
                break

            if hasattr(base, 'ancestors'):
                ancestors += base.ancestors(top)

        return ancestors


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


    def __setitem__(self, key, value):
        super(CustomOrderedDict, self).__setitem__(key, value)
        self.order.append(key)


    def __delitem__(self, key):
        super(CustomOrderedDict, self).__delitem__(key)
        self.order.remove(key)


    def __iter__(self):

       return CustomOrderedDictIterator(self, 'values')


    def iteritems(self):
        return CustomOrderedDictIterator(self, 'items')


    def iterkeys(self):
        return CustomOrderedDictIterator(self, 'keys')


    def keys(self):
        return self.order



class CustomOrderedDictIterator(object):

    obj = None
    mode = None
    current_idx = None


    def __init__(self, obj, mode):

        """
        Params:
            obj: The object to iterate over
            mode: Iterator mode, one of: 'items', 'keys', 'values'
        """

        self.obj = obj
        self.mode = mode
        self.current_idx = 0


    def __iter__(self):
        return self


    def next(self):

        if self.current_idx >= len(self.obj.keys()):
            raise StopIteration()

        key = self.obj.keys()[self.current_idx]
        if self.mode == 'keys':
            rv = key

        elif self.mode == 'values':
            rv = self.obj[key]

        elif self.mode == 'items':
            rv = (key, self.obj[key])

        self.current_idx = self.current_idx + 1
        return rv
