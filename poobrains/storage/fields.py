# -*- coding: utf-8 -*-

# external imports
import flask
import peewee

from peewee import Check

# parent imports
#import poobrains
import poobrains.helpers
import poobrains.form


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

        except Exception:

            self.fail("Invalid handle '%s' for %s." % (value, self.storable.__name__))

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

    form_widget = poobrains.form.fields.Field
    type = poobrains.form.types.STRING

    def __init__(self, *args, **kwargs):

        if kwargs.has_key('form_widget'):
            self.form_widget = kwargs.pop('form_widget')

        super(Field, self).__init__(*args, **kwargs)


    def form(self):

        kw = {}
        kw['name'] = self.name
        kw['type'] = self.type
        kw['default'] = self.default

        if self.verbose_name:
            kw['label'] = self.verbose_name
            kw['placeholder'] = self.verbose_name
        else:
            kw['placeholder'] = self.name
        
        if self.null == False and self.default is None:
            kw['required'] = True
        else:
            kw['required'] = False

        return self.form_widget(**kw)


class IntegerField(Field, peewee.IntegerField):
    type = poobrains.form.types.INT


class CharField(Field, peewee.CharField):
    type = poobrains.form.types.STRING


class TextField(Field, peewee.TextField):

    form_widget = poobrains.form.fields.TextArea
    type = poobrains.form.types.STRING


class DateTimeField(Field, peewee.DateTimeField):

    type = poobrains.form.types.DATETIME
    form_widget = poobrains.form.fields.DateTime


class ForeignKeyField(Field, peewee.ForeignKeyField):

    # NOTE: type set by constructor, because it needs a storable passed in 
    form_widget = ForeignKeyChoice

    def __init__(self, rel_model, **kwargs):

        super(ForeignKeyField, self).__init__(rel_model, **kwargs)
        self.type = StorableInstanceParamType(rel_model) # basically just needed for the CLI, which checks field.type


class BooleanField(Field, peewee.BooleanField):

    form_widget = poobrains.form.fields.Checkbox
    type = poobrains.form.types.BOOL
