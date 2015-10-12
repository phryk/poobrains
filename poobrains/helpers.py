# -*- coding: utf-8 -*-

from collections import OrderedDict


def choose_primary(d):
    
    for k,v in d.iteritems():

        if v['primary']:
           return v

    return d.values()[0]


class ChildAware(object):

    @classmethod
    def children(cls):

        children = cls.__subclasses__()

        for child in children:
            children += child.children()

        return children


    @classmethod
    def ancestors(cls, top=None):

        """
        params:
            * top: class, when this class is reached, the iteration is stopped
        """

        if top is None:
            top = ChildAware

        whitelist = [top] + top.children()
        ancestors = []

        for base in cls.__bases__:

            if base in whitelist:
                ancestors.append(base)

                if base is top:
                    break

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
