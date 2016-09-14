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


class Field(object):

    __metaclass__ = poobrains.helpers.MetaCompatibility

    _empty = None # hint if value of this field was set to empty_value
    errors = None
    prefix = None
    name = None
    value = None
    empty_value = '' # value which is considered to be "empty"
    default = None # used when client sends no value for this field
    label = None
    placeholder = None
    readonly = None
    required = None
    validator = validators.is_string
    coercer = coercers.coerce_string

    class Meta:
        clone_props = ['name', 'value', 'label', 'placeholder', 'readonly', 'required', 'validator', 'default']


    def __init__(self, name=None, value=None, label=None, placeholder=None, readonly=False, required=False, validator=None, default=None):

        self.errors = []
        self.name = name
        self.value = value
        self.label = label if label else name
        self.placeholder = placeholder if placeholder else name
        self.readonly = readonly
        self.required = required
        self.rendered = False
        self.default = default
        
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

    
    def empty(self):
        return self.value == self.empty_value

    
    def validate(self):

        poobrains.app.debugger.set_trace()

        if not self.empty():
            self.validator(self.value)

        elif self.required:
            raise errors.ValidationError("Required field '%s' was left empty." % self.name)

    
    def bind(self, value):

        if isinstance(value, errors.MissingValue):
            self.value = self.default() if callable(self.default) else self.default

        else:
            try:
                self.value = self.coercer(value)

                if self.required and self.empty():
                    self.value = self.default() if callable(self.default) else self.default


            except ValueError:
                e = errors.ValidationError("%s failed with value '%s'." % (self.coercer.__name__, value))
                self.errors.append(re)
                raise e

        try:
            self.validate() # escalates any ValidationErrors (or others) to caller
        except errors.ValidationError as e:
            self.errors.append(e)
            raise


class Value(Field):
    """ To put a static value into the form. """

    def validate(self):
        pass


    def bind(self, value):
        pass


class RenderableField(Field, poobrains.rendering.Renderable):

    rendered = None


    def render(self):

        self.rendered = True
        return super(RenderableField, self).render()


class Message(RenderableField):

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.value)

    
    def validate(self):
        pass


    def bind(self, value):
        pass


class Text(RenderableField):
    pass


class ObfuscatedText(Text):
    pass


class TextArea(Text):
    pass


class Integer(RenderableField):
    validator = validators.is_integer 


class RangedInteger(Integer):

    min = None
    max = None


    def validate(self):

        super(RangedInteger, self).validate()

        if not self.empty():

            if self.value < self.min or self.value > self.max:
                raise errors.ValidationError("%s: %d is out of range. Must be in range from %d to %d." % (self.name, self.value, self.min, self.max))


class Choice(RenderableField):

    multi = False
    choices = None
    empty_label = 'Please choose'
    
    def __init__(self, *args, **kwargs):

        if kwargs.has_key('choices'):
            choices = kwargs.pop('choices')
        else:
            choices = []

        super(Choice, self).__init__(*args, **kwargs)
        self.choices = choices


    def validate(self):

        if not self.value in dict(self.choices).keys(): # FIXME: I think this will fuck up, at least for optgroups
            raise errors.ValidationError("'%s' is not an approved choice for %s.%s" % (self.value, self.prefix, self.name))


class MultiChoice(Choice):

    multi = True

    def validate(self):
        
        for value in values:
            super(MultiChoice, self).validate() # FIXME: This is nonsense.


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
        #poobrains.app.debugger.set_trace()
        super(ForeignKeyChoice, self).__init__(*args, **kwargs)


    def __setattr__(self, name, value):

        if name == 'value' and isinstance(value, poobrains.storage.Storable):
            return super(ForeignKeyChoice, self).__setattr__(name, value._get_pk_value())

        super(ForeignKeyChoice, self).__setattr__(name, value)


class Checkbox(RenderableField):

    empty_value = False
    default = False
    coercer = coercers.coerce_bool
    validator = validators.is_bool



class Float(RenderableField):
    validator = validators.is_float


class RangedFloat(RangedInteger):
    validator = validators.is_float


class Keygen(RenderableField):
    
    challenge = None

    def __init__(self, *args, **kw):

        try:
            if flask.request.method == 'GET':
                poobrains.app.logger.debug("Keygen new challenge")
                self.challenge = helpers.random_string()
        except RuntimeError as e:
            pass

        super(Keygen, self).__init__(*args, **kw)


class File(RenderableField):
    pass
