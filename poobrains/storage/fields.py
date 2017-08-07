# -*- coding: utf-8 -*-

# external imports
import peewee

# parent imports
#import poobrains
import poobrains.helpers
import poobrains.form


class Field(poobrains.helpers.ChildAware):

    form_class = poobrains.form.fields.Text

    def __init__(self, *args, **kwargs):

        if kwargs.has_key('form_class'):
            self.form_class = kwargs.pop('form_class')

        super(Field, self).__init__(*args, **kwargs)


    def form(self, value):
        return self.form_class(self.name, label=self.name, value=value)


class IntegerField(Field, peewee.IntegerField):
    pass


class CharField(Field, peewee.CharField):
    pass


class TextField(Field, peewee.TextField):
    form_class = poobrains.form.fields.TextArea


class DateTimeField(Field, peewee.DateTimeField):
    form_class = poobrains.form.fields.DateTime


class ForeignKeyField(Field, peewee.ForeignKeyField):
    form_class = poobrains.form.fields.ForeignKeyChoice


class BooleanField(Field, peewee.BooleanField):
    form_class = poobrains.form.fields.Checkbox
