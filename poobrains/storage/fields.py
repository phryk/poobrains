# -*- coding: utf-8 -*-

# external imports
import peewee

# parent imports
from poobrains import helpers
from poobrains import form


class Field(helpers.ChildAware):
    pass # Just a shell class to enable geting all poobrains.storage fields as Field.children()


class CharField(peewee.CharField, Field):
    pass


class TextField(peewee.TextField, Field):
    pass


class FileField(peewee.ForeignKeyField, Field):
    
    def __init__(self, *args, **kwargs):

        from poobrains.storage import File

        rel_model = File

        super(FileField, self).__init__(rel_model, *args, **kwargs)
