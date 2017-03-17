# -*- coding: utf-8 -*-

# external imports
import peewee

# parent imports
from poobrains import helpers
from poobrains import form
import poobrains


class Field(helpers.ChildAware):

    form_class = form.fields.Text

    def __init__(self, *args, **kwargs):

        if kwargs.has_key('form_class'):
            self.form_class = kwargs.pop('form_class')

        super(Field, self).__init__(*args, **kwargs)


    def form(self, value):
        return self.form_class(self.name, label=self.name, value=value)


class IntegerField(peewee.IntegerField, Field):
    pass


class CharField(peewee.CharField, Field):
    pass


class TextField(peewee.TextField, Field):
    form_class = poobrains.form.fields.TextArea


class DateTimeField(peewee.DateTimeField, Field):
    pass


class ForeignKeyField(peewee.ForeignKeyField, Field):
    form_class = form.fields.ForeignKeyChoice


class BooleanField(peewee.BooleanField, Field):
    form_class = form.fields.Checkbox


class FileField(ForeignKeyField):
    
    def __init__(self, *args, **kwargs):

        rel_model = poobrains.storage.fields.File

        super(FileField, self).__init__(rel_model, *args, **kwargs)


