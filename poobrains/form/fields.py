# -*- coding: utf-8 -*-

import flask

# parent imports
import poobrains
from poobrains import rendering, helpers

# internal imports
import validators


class Field(rendering.Renderable):

    name = None
    value = None
    label = None
    placeholder = None
    readonly = None
    validators = None
    rendered = None


    def __init__(self, name=None, value=None, label=None, placeholder=None, readonly=False, validators=[]):

        self.name = name
        self.value = value
        self.label = label if label else name
        self.placeholder = placeholder if placeholder else name
        self.readonly = readonly
        self.validators = validators
        self.rendered = False


    def __getattr__(self, name):

        if name in ['label', 'placeholder']:

            real_value = super(Field, self).__getattr__(name)

            if not real_value and isinstance(self.name, basestring):
                return self.name.capitalize()

            return real_value


    def validate(self, value):

        for validator in self.validators:
            if not validator(value):
                return False

        return True


    def template_candidates(self, mode):

        field_type = self.__class__.__name__.lower()

        tpls = []
        tpls.append("form/fields/%s-%s.jinja" % (self.name, field_type))
        tpls.append("form/fields/%s.jinja" % field_type)
        tpls.append("form/fields/field.jinja")

        return tpls


    def render(self, mode='full'):

        self.rendered = True
        return super(Field, self).render(mode)


class Message(Field):
    pass


class Text(Field):
    pass


class ObfuscatedText(Text):
    pass


class TextArea(Text):
    pass


class Integer(Field):

    def __init__(self, name, value=None, label=None, readonly=False, validators=[]):

        validators.append(validators.is_int)
        super(Integer, self).__init__(name, value=value, label=label, readonly=readonly, validators=validators)


class RangedInteger(Integer):

    min = None
    max = None

    def __init__(self, name, value=None, label=None, min=0, max=100, readonly=False, validators=[]):

        self.min = min
        self.max = max

        validators.append(validators.mk_min(self.min))
        validators.append(validators.mk_max(self.max))

        super(RangedInteger, self).__init__(name, value=value, label=label, readonly=readonly, validators=validators)


class Float(Field):

    def __init__(self, name, value=None, label=None, readonly=False, validators=[]):

        validators.append(validators.is_float)
        super(Float, self).__init__(name, value=value, label=label, readonly=readonly, validators=validators)


class RangedFloat(Float):

    min = None
    max = None

    def __init__(self, name, value=None, label=None, min=0, max=100, step=0.1, validators=[]):

        self.min = min
        self.max = max

        validators.append(validators.mk_min(self.min))
        validators.append(validators.mk_max(self.max))

        super(RangedFloat, self).__init__(name, value=value, label=label, validators=validators)


class IntegerChoice(Integer):

    choices = None

    def __init__(self, name=None, choices=None, value=None, label=None, placeholder=None, readonly=False, validators=[]):

        self.choices = choices if choices else {}
        super(IntegerChoice, self).__init__(name, value=value, label=label, placeholder=placeholder, readonly=readonly, validators=validators)

    def validate(self, value):

        return super(IntegerChoice, self).validate(value) and value in self.choices.keys()


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
