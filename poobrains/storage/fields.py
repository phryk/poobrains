# -*- coding: utf-8 -*-

# external imports
import flask
import peewee

from peewee import AutoField, Check

# parent imports
from poobrains import app
import poobrains.helpers
import poobrains.form


# hack
AutoField.form_widget = None # makes sure AutoField is ignored in AutoForms


class StorableInstanceParamType(poobrains.form.types.ParamType):

    storable = None
    choices = None

    def __init__(self, storable, choices=None):

        super(StorableInstanceParamType, self).__init__()

        self.storable = storable
        self.choices = choices


    def convert(self, value, param, ctx):

        if value == '':
            return None

        if isinstance(value, self.storable):
            return value # idempotency/gigo/ducks


        try:
            instance = self.storable.load(value)

        except self.storable.DoesNotExist:

            self.fail("No such %s: %s." % (self.storable.__name__, value))

        if self.choices is not None and instance not in self.choices:
            self.fail("'%s' is not an approved choice." % value)

        return instance

poobrains.form.types.StorableInstanceParamType = StorableInstanceParamType


class ForeignKeyChoice(poobrains.form.fields.Text):

    """
    Note: This field expects to be bound to a ForeignKeyField.
    Note: This is a FORM field, not a storage field.
    """

    __metaclass__ = poobrains.form.fields.BoundFieldMeta

    storable = None

    def __init__(self, fkfield, choices=None, **kwargs):

        self.storable = fkfield.rel_model
                
        if not choices:

            choices = []
            for choice in self.storable.list('read', flask.g.user):
                choices.append((choice, choice.title))

        kwargs['choices'] = choices

        kwargs['type'] = StorableInstanceParamType(self.storable, choices=[choice for choice, _ in choices])

        super(ForeignKeyChoice, self).__init__(**kwargs)

poobrains.form.fields.ForeignKeyChoice = ForeignKeyChoice


class Field(poobrains.helpers.ChildAware):

    form_widget = poobrains.form.fields.Text
    type = poobrains.form.types.STRING

    def __init__(self, *args, **kwargs):

        if kwargs.has_key('form_widget'):
            self.form_widget = kwargs.pop('form_widget')

        super(Field, self).__init__(*args, **kwargs)


    def form(self):

        if self.form_widget is None: # allows fields to be left out of forms
            return None

        kw = {}
        kw['name'] = self.name
        kw['type'] = self.type
        kw['default'] = self.default
        kw['help_text'] = self.help_text

        if self.verbose_name:
            kw['label'] = self.verbose_name
            kw['placeholder'] = self.verbose_name
        else:
            kw['placeholder'] = self.name
        
        if self.null == False and self.default is None:
            kw['required'] = True
        else:
            kw['required'] = False

        if self.choices:
            kw['choices'] = self.choices

        return self.form_widget(**kw)


class IntegerField(Field, peewee.IntegerField):
    type = poobrains.form.types.INT


class FloatField(Field, peewee.FloatField):
    type = poobrains.form.types.FLOAT


class DoubleField(Field, peewee.DoubleField):
    type = poobrains.form.types.FLOAT


class CharField(Field, peewee.CharField):
    type = poobrains.form.types.STRING


class TextField(Field, peewee.TextField):

    form_widget = poobrains.form.fields.TextArea
    type = poobrains.form.types.STRING


class DateTimeField(Field, peewee.DateTimeField):

    type = poobrains.form.types.DATETIME
    form_widget = poobrains.form.fields.DateTime


class ForeignKeyField(Field, peewee.ForeignKeyField):

    form_widget = ForeignKeyChoice

    def bind(self, model, name, set_attribute=True):
    
        # NOTE: type set in here because it needs a Storable class passed in 

        super(ForeignKeyField, self).bind(model, name, set_attribute=set_attribute)
        self.type = StorableInstanceParamType(self.rel_model) # basically just needed for the CLI, which checks field.type


class BooleanField(Field, peewee.BooleanField):

    form_widget = poobrains.form.fields.Checkbox
    type = poobrains.form.types.BOOL
