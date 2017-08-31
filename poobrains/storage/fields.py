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

    def __init__(self, storable):

        super(StorableInstanceParamType, self).__init__()
        self.storable = storable


    def convert(self, value, param, ctx):

        if isinstance(value, self.storable):
            return value # idempotency/gigo/ducks


        try:
            return self.storable.load(value)

        except Exception:

            self.fail("Invalid handle '%s' for %s." % (value, self.storable.__name__))

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

        import pudb; pudb.set_trace()
        self.storable = fkfield.rel_model
        super(ForeignKeyChoice, self).__init__(**kwargs)
                
        #TODO: is this the place to do permission checking for the field?

        if choices is None:

            choices = []
            for choice in self.storable.list('read', flask.g.user):
                if hasattr(choice, 'name') and choice.name:
                    choice_name = choice.name
                else:
                    choice_name = "%s #%d" % (choice.__class__.__name__, choice.id)

                choices.append((choice.handle_string, choice_name))

        #self.type = poobrains.form.types.Choice(choices = [instance for instance, label in choices])
        self.type = StorableInstanceParamType(self.storable)


    def validate(self):

        if not self.value is None:
            if not isinstance(self.value, self.storable):
                raise poobrains.errors.ValidationError("Unknown %s handle '%s'." % (self.storable.__name__, self.value))
        elif self.required:
            raise poobrains.errors.ValidationError("Field %s is required." % self.name)

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


