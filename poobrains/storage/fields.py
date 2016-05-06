# -*- coding: utf-8 -*-

# external imports
import peewee

# parent imports
from poobrains import helpers
from poobrains import form


class Field(helpers.ChildAware):

    form_class = form.fields.Text
    form_extra_validators = []

    def form(self, value):
        return form_class(self.name, label=self.name, value=value)


class CharField(peewee.CharField, Field):
    pass


class TextField(peewee.TextField, Field):
    pass


class DateTimeField(peewee.DateTimeField, Field):
    pass


class ForeignKeyField(peewee.ForeignKeyField):
    pass


class BooleanField(peewee.BooleanField, Field):
    pass


class FileField(peewee.ForeignKeyField, Field):
    
    def __init__(self, *args, **kwargs):

        from poobrains.storage import File

        rel_model = File

        super(FileField, self).__init__(rel_model, *args, **kwargs)


