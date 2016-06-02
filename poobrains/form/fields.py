# -*- coding: utf-8 -*-

import flask

# parent imports
import poobrains
from poobrains import rendering, helpers

# internal imports
import errors
import validators
import coercers


class Field(rendering.Renderable):

    prefix = None
    name = None
    value = None
    label = None
    placeholder = None
    readonly = None
    validator = validators.is_str
    coercer = coercers.coerce_string
    rendered = None


    def __init__(self, name=None, value=None, label=None, placeholder=None, readonly=False, validator=None):

        self.name = name
        self.value = value
        self.label = label if label else name
        self.placeholder = placeholder if placeholder else name
        self.readonly = readonly
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

    
    def validate(self, value):
        self.validator(value)

    
    def bind(self, value):
        #print "%s.bind" % self.__class__.__name__
        #print self, value
        self.value = self.coercer(value)


    def render(self):

        self.rendered = True
        return super(Field, self).render()


class Message(Field):
    coercer = None # Makes this field be ignored when checking for missing form data

class Text(Field):
    pass


class ObfuscatedText(Text):
    pass


class TextArea(Text):
    pass


class Integer(Field):
    validator = validators.is_int 


class RangedInteger(Integer):

    min = None
    max = None


#    def __init__(self, name, value=None, label=None, min=0, max=100, readonly=False, validators=[]):
#
#        self.min = min
#        self.max = max
#
#        validators.append(validators.mk_min(self.min))
#        validators.append(validators.mk_max(self.max))
#
#        super(RangedInteger, self).__init__(name, value=value, label=label, readonly=readonly, validators=validators)

    def validate(self, value):

        self.validator(value)
        x = int(value)
        if x <self. min or x > self.max:
            raise errors.ValidationError("%s: %d is out of range. Must be in range from %d to %d." % (self.name, value, self.min, self.max))


class Checkbox(RangedInteger):

    min = 0
    max = 1

    coercer = coercers.coerce_bool


class Float(Field):
    validator = validators.is_float


class RangedFloat(RangedInteger):
    validator = validators.is_float


class IntegerChoice(Integer):

    choices = None
    validator = validators.is_int
    coercer = coercers.coerce_int


    def __init__(self, name=None, choices=None, value=None, label=None, placeholder=None, readonly=False, validator=None):

        self.choices = choices if choices else {}
        super(IntegerChoice, self).__init__(name, value=value, label=label, placeholder=placeholder, readonly=readonly, validator=validator)

    def validate(self, value):

        super(IntegerChoice, self).validate(value)

        integer_value = self.coerce(value)
        if integer_value not in self.choices:
            raise error.ValidationError("%d is not an approved choice for %s.%s" % (integer_value, self.prefix, self.name))


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
