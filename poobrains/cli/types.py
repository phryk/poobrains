# -*- coding: utf-8 -*-

import click

import poobrains.storage

class StorableParamType(click.ParamType):

    baseclass = None

    def __init__(self, baseclass=poobrains.storage.Storable):

        super(StorableParamType, self).__init__()
        self.baseclass = baseclass

    def convert(self, value, param, ctx):

        import pudb; pudb.set_trace()

        if isinstance(value, self.baseclass):
            return value # apparently we need this function to be idempotent? Didn't even knew that was a real word.

        storables = {k.lower(): v for k, v in self.baseclass.class_children_keyed().iteritems()}

        if storables.has_key(value.lower()):
            return storables[value.lower()] # holy shit it's lined up! D:

        self.fail(u'Not a valid storable: %s. Try one of %s' % (value, storables.keys()))


STORABLE = StorableParamType()
