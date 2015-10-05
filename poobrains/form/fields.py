# -*- coding: utf-8 -*-

# parent imports
from poobrains import rendering

# internal imports
import validators


class Field(rendering.Renderable):

    name = None
    value = None
    label = None
    placeholder = None
    readonly = None
    validators = None


    def __init__(self, name, value=None, label=None, readonly=False, validators=[]):

        self.name = name
        self.value = value
        self.label = label if label else name
        self.readonly = readonly
        self.validators = validators


    def validate(self, value):

        for validator in self.validators:
            if not validator(value):
                return False

        return True


    def template_candidates(self, mode):

        field_type = self.__class__.__name__.lower()

        tpls = []
        tpls.append("fields/%s-%s.jinja" % (self.name, field_type))
        tpls.append("fields/%s.jinja" % field_type)
        tpls.append("fields/field.jinja")

        return tpls


class Warning(Field):
    pass


class Text(Field):
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


class File(Field):
    pass