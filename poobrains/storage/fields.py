# -*- coding: utf-8 -*-

# external imports
import flask
import peewee

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


class ForeignKeyChoice(poobrains.form.fields.TextAutoComplete):

    """
    Note: This field expects to be bound to a ForeignKeyField.
    Note: This is a FORM field, not a storage field.
    """

    __metaclass__ = poobrains.form.fields.BoundFieldMeta

    storable = None

    def __new__(cls, fkfield, *args, **kwargs):
        return super(ForeignKeyChoice, cls).__new__(cls, *args, **kwargs)


    def __init__(self, fkfield, choices=None, **kwargs):

        self.storable = fkfield.rel_model
        super(ForeignKeyChoice, self).__init__(**kwargs)
                
        if not choices:

            choices = []
            for choice in self.storable.list('read', flask.g.user):
                choices.append((choice, choice.title))

        self.choices = choices

        #self.type = poobrains.form.types.Choice(choices = [instance for instance, label in choices])
        self.type = StorableInstanceParamType(self.storable, choices=[choice for choice, _ in choices])


    def validate(self):

        if not self.value is None:
            if not isinstance(self.value, self.storable):
                raise poobrains.form.errors.ValidationError("Unknown %s handle '%s'." % (self.storable.__name__, self.value))
        elif self.required:
            raise poobrains.form.errors.ValidationError("Field %s is required." % self.name)

poobrains.form.fields.ForeignKeyChoice = ForeignKeyChoice



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
    form_class = ForeignKeyChoice


class BooleanField(Field, peewee.BooleanField):
    form_class = poobrains.form.fields.Checkbox


