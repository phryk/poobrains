# -*- coding: utf-8 -*-

import flask

# parent imports
import poobrains
from poobrains import rendering, helpers

# internal imports
import errors
import validators
import coercers


class BoundFieldMeta(poobrains.helpers.MetaCompatibility, poobrains.helpers.ClassOrInstanceBound):
    pass


class Field(rendering.Renderable):

    errors = None
    prefix = None
    name = None
    value = None
    empty_value = ''
    missing_value = None
    label = None
    placeholder = None
    readonly = None
    required = None
    validator = validators.is_string
    coercer = coercers.coerce_string
    rendered = None


    def __init__(self, name=None, value=None, label=None, placeholder=None, readonly=False, required=False, validator=None):

        self.errors = []
        self.name = name
        self.value = value
        self.label = label if label else name
        self.placeholder = placeholder if placeholder else name
        self.readonly = readonly
        self.required = required
        self.rendered = False
        
        if validator:
            self.validator = validator


    def __getattr__(self, name):

        if name in ['label', 'placeholder']:

            real_value = super(Field, self).__getattr__(name)

            if not real_value and isinstance(self.name, basestring):
                return self.name.capitalize()

            return real_value


    @classmethod
    def templates(cls, mode=None):

        tpls = []

        for x in [cls] + cls.ancestors():

            name = x.__name__.lower()

            if issubclass(x, Field):

                tpls.append('form/fields/%s.jinja' % name)
                
                if mode:
                    tpls.append('form/fields/%s-%s.jinja' % (name, mode))

            else:

                tpls.append('%s.jinja' % name)

                if mode:
                    tpls.append('%s-%s.jinja' % (name, mode))

        return tpls

    
    def empty(self, value=None):
        if value is None:
            value = self.value
        return value == self.empty_value

    
    def validate(self, value):
        if not self.empty(value):
            self.validator(value)

        elif self.required:
            raise errors.ValidationError("Required field '%s' was left empty." % self.name)

    
    def bind(self, value):

        if self.empty(value):
            self.value = self.empty_value
        else:
            self.value = self.coercer(value)


    def render(self):

        self.rendered = True
        return super(Field, self).render()


class Message(Field):
    coercer = None # Makes this field be ignored when checking for missing form data

class Value(Field):
    pass


class Text(Field):
    pass


class ObfuscatedText(Text):
    pass


class TextArea(Text):
    pass


class Integer(Field):
    validator = validators.is_integer 


class RangedInteger(Integer):

    min = None
    max = None
    
    def validate(self, value):

        self.validator(value)
        x = int(value)
        if x <self. min or x > self.max:
            raise errors.ValidationError("%s: %d is out of range. Must be in range from %d to %d." % (self.name, value, self.min, self.max))


class Choice(Field):

    multi = False
    choices = None
    
    def __init__(self, name=None, choices=[],  value=None, label=None, placeholder=None, readonly=False, required=False, validator=None):

        super(Choice, self).__init__(name=name, value=value, label=label, placeholder=placeholder, readonly=readonly, required=required, validator=validator)
        self.choices = choices


    def validate(self, value):

        super(Choice, self).validate(value)

        if not self.coercer(value) in dict(self.choices).keys():
            raise errors.ValidationError("'%s' is not an approved choice for %s.%s" % (value, self.prefix, self.name))


class MultiChoice(Choice):

    multi = True

    def validate(self, values):
        
        for value in values:
            super(MultiChoice, self).validate(value)


    def bind(self, values):
        
        self.value = []

        for value in values:
            self.value.append(self.coercer(value))


class TextChoice(Choice):
    validator = validators.is_string
    coercer = coercers.coerce_string


class MultiTextChoice(MultiChoice):
    validator = validators.is_string
    coercer = coercers.coerce_string


class IntegerChoice(Choice):
    validator = validators.is_integer
    coercer = coercers.coerce_int


class MultiIntegerChoice(MultiChoice):
    validator = validators.is_integer
    coercer = coercers.coerce_int


class ForeignKeyChoice(IntegerChoice):

    """
    Warning: this field expects to be bound to a ForeignKeyField.
    """

    __metaclass__ = BoundFieldMeta

    storable = None

    def __new__(cls, fkfield, *args, **kwargs):
        return super(ForeignKeyChoice, cls).__new__(cls, *args, **kwargs)


    def __init__(self, fkfield, *args, **kwargs):

        self.storable = fkfield.rel_model
        # TODO build default choices if not passed
        super(ForeignKeyChoice, self).__init__(*args, **kwargs)


    def __setattr__(self, name, value):

        if name == 'value':
            if value == '':
                return super(ForeignKeyChoice, self).__setattr__(name, None) # empty string counts as no value in HTML select
            elif isinstance(value, poobrains.storage.Storable):
                return super(ForeignKeyChoice, self).__setattr__(name, value._get_pk_value())

        super(ForeignKeyChoice, self).__setattr__(name, value)


class Checkbox(RangedInteger):

    empty_value = False
    missing_value = False
    min = 0
    max = 1

    coercer = coercers.coerce_bool

    def empty(self, value=None):

        if value is None:
            value = self.value

        return value != ''


class Float(Field):
    validator = validators.is_float


class RangedFloat(RangedInteger):
    validator = validators.is_float




class Keygen(Field):
    
    challenge = None

    def __init__(self, *args, **kw):

        try:
            if flask.request.method == 'GET':
                poobrains.app.logger.debug("Keygen new challenge")
                self.challenge = helpers.random_string()
        except RuntimeError as e:
            pass

        super(Keygen, self).__init__(*args, **kw)


class File(Field):
    pass
