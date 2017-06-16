# -*- coding: utf-8 -*-

# external imports
import peewee

# parent imports
import poobrains


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
    pass


class ForeignKeyField(Field, peewee.ForeignKeyField):
    form_class = poobrains.form.fields.ForeignKeyChoice


class BooleanField(Field, peewee.BooleanField):
    form_class = poobrains.form.fields.Checkbox


class FileField(ForeignKeyField):
    
    def __init__(self, *args, **kwargs):

        rel_model = poobrains.storage.fields.File

        super(FileField, self).__init__(rel_model, *args, **kwargs)


