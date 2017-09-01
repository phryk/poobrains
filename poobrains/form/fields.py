# -*- coding: utf-8 -*-

import time # needed for ordered attributes
import datetime
import flask

# parent imports
#import poobrains
from poobrains import app
import poobrains.helpers
import poobrains.rendering

# internal imports
from . import errors
from . import validators
from . import types


def value_string(value):
    """ Create a string representation of this fields value for use in HTML """

    if value is None:
        return ''

    elif isinstance(value, bool):
        return 't' if value == True else 'f'

    elif isinstance(value, datetime.datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')

    elif hasattr(value, 'handle_string'): # can't check whether this is a Storable by with isinstance because we can't depend on storage here (since storage depends on form )
        return value.handle_string

    else:
        return unicode(value)


def empty(value, multi=False):
    return value == '' or (multi and value == [''])


class BoundFieldMeta(poobrains.helpers.MetaCompatibility, poobrains.helpers.ClassOrInstanceBound):
    pass


class Field(object):

    __metaclass__ = poobrains.helpers.MetaCompatibility

    _created = None
    form = None # only filled if this is a field rendered outside of the form
    errors = None
    prefix = None
    name = None
    type = types.STRING
    value = None
    choices = None
    #empty_value = '' # value which is considered to be "empty"
    default = None # used when client sends no value for this field
    label = None
    multi = False # Whether this field takes multiple values (i.e. value passed to .bind will be a list)
    placeholder = None
    readonly = None
    required = None
    validator = validators.is_string

    class Meta:
        clone_props = ['name', 'value', 'label', 'placeholder', 'readonly', 'required', 'validator', 'default']


    def __new__(cls, *args, **kwargs):

        instance = super(Field, cls).__new__(cls, *args, **kwargs)
        instance._created = time.time()

        return instance


    def __init__(self, name=None, type=None, value=None, choices=None, label=None, placeholder=None, readonly=False, required=False, validator=None, default=None, form=None, **kwargs):

        self.errors = []
        self.name = name
        self.value = value
        self.choices = choices
        self.label = label if label is not None else name
        self.placeholder = placeholder if placeholder else self.label
        self.readonly = readonly
        self.required = required
        self.rendered = False

        if not type is None:
            self.type = type

        if not default is None:
            self.default = default
        
        if not validator is None:
            self.validator = validator

        
        if not form is None:

            self.form = form
            if self.form.prefix:
                self.prefix = "%s.%s" % (self.form.prefix, self.form.name)
            else:
                self.prefix = self.form.name
            self.form._add_external_field(self)


    def __getattr__(self, name):

        if name in ['label', 'placeholder']:

            real_value = super(Field, self).__getattr__(name)

            if not real_value and isinstance(self.name, basestring):
                return self.name.capitalize()

            return real_value


    def templates(self, mode=None):

        tpls = []

        for x in [self.__class__] + self.__class__.ancestors():

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
        #return self.value == self.empty_value
        return empty(self.value)


    def validate(self):

        if not self.validator:
            return

        if not self.empty():
            self.validator(self.value)

        elif self.required:
            raise errors.ValidationError("Required field '%s' was left empty." % self.name)


    def bind(self, value):
        
        if empty(self.value):
            self.value = self._default

        else:
            try:
                self.value = self.type.convert(value, None, None)

                #if self.required and self.empty():
                if self.empty():
                    self.value = self._default


            except errors.BadParameter:
                e = errors.ValidationError("Invalid input '%s' for field %s." % (value, self.name))
                self.errors.append(e)
                raise e

        try:
            self.validate()
        except errors.ValidationError as e:
            self.errors.append(e)
            raise

    @property
    def _default(self):
        #return self.type.convert(self.default() if callable(self.default) else self.default, None, None)
        return self.default() if callable(self.default) else self.default


    @property
    def value_string(self):

        if self.multi:
            strings = []
            for subvalue in self.value:
                strings.append(value_string(subvalue))

            return strings

        return value_string(self.value)


    @property
    def choices_string(self):

        pairs = []

        if self.choices is not None:

            for choice, label in self.choices:

                if isinstance(choice, (list, tuple)):

                    subchoices = []

                    for subchoice, sublabel in choice:
                        subchoices.append((value_string(subchoice), sublabel))

                    pairs.append((subchoices, label))

                else:
                    pairs.append((value_string(choice), label))

        return pairs


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


class TextAutoComplete(Text):
    
    class Meta:
        clone_props = ['name', 'value', 'label', 'placeholder', 'readonly', 'required', 'validator', 'default', 'choices']

    choices = None

    def __init__(self, choices=None, **kwargs):
        
        super(TextAutoComplete, self).__init__(**kwargs)

        if choices is None:
            choices = []

        self.choices = choices
        self.type = types.Choice([value for value, label in choices]) # FIXME: Changing self.choices in place will lead to inconsistency


class ObfuscatedText(Text):
    pass


class TextArea(Text):
    pass


class Integer(RenderableField):
    default = 0
    validator = validators.is_integer
    type = types.INT


class RangedInteger(Integer):

    min = None
    max = None


    def validate(self):

        super(RangedInteger, self).validate()

        if not self.empty():

            if self.value < self.min or self.value > self.max:
                raise errors.ValidationError("%s: %d is out of range. Must be in range from %d to %d." % (self.name, self.value, self.min, self.max))


class DateTime(RenderableField):

    validator = validators.is_datetime
    type = types.DATETIME


class Choice(RenderableField):

    choices = None
    empty_label = 'Please choose'
    multi = False
    
    class Meta:
        clone_props = ['name', 'value', 'label', 'placeholder', 'readonly', 'required', 'validator', 'default', 'choices', 'empty_label', 'multi']
    
    def __init__(self, choices=None, type=None, **kwargs):

        if choices is None:
            choices = []

        self.choices = []
        for choice, label in choices:
            self.choices.append((self.type.convert(choice, None, None), label))

        #self.type = types.Choice(choices=[self.type.convert(value) for label, value in choices])

        super(Choice, self).__init__(**kwargs)

    
    def validate(self):
        
        choices = self.choices() if callable(self.choices) else self.choices
        if not self.value in dict(choices).keys(): # FIXME: I think this will fuck up, at least for optgroups
            raise errors.ValidationError("'%s' is not an approved choice for %s.%s" % (self.value, self.prefix, self.name))


class MultiChoice(Choice):

    multi = True
    default = []
    #empty_value = []

    def __init__(self, **kwargs):
        super(MultiChoice, self).__init__(**kwargs)

        if self.value is None:
            self.value = []

    
#    def empty(self):
#
#        if self.value == self.empty_value or len(self.value) == 0:
#            return True
#
#        for value in self.value:
#            if value != '':
#                try:
#                    self.type.convert(value, None, None)
#                    return False
#                
#                except errors.BadParameter:
#                    pass
#
#        return True # default to True if no coercible non-'' values where found


    def validate(self):

        for value in self.value:
            if value != '' and not value in dict(self.choices).keys(): # FIXME: I think this will fuck up, at least for optgroups
                raise errors.ValidationError("'%s' is not an approved choice for %s.%s" % (self.value, self.prefix, self.name))


    def bind(self, values):
        
        if empty(values, multi=True):
            self.value = self._default

        else:

            self.value = [] # clear any already existing values

            for value in values:
                try:
                    self.value.append(self.type.convert(value, None, None))
                
                except errors.BadParameter as e:
                    error = errors.ValidationError("Invalid input '%s' for field %s. Error message: %s" % (value, self.name, e.message))
                    self.errors.append(error)
                    raise error

            try:
                self.validate()
            except errors.ValidationError as e:
                self.errors.append(e)
                raise


class TextChoice(Choice):
    validator = validators.is_string


class MultiTextChoice(MultiChoice):
    validator = validators.is_string


class IntegerChoice(Choice):
    validator = validators.is_integer


class MultiIntegerChoice(MultiChoice):
    validator = validators.is_integer


class Checkbox(RenderableField):

    class Meta:
        clone_props = ['name', 'value', 'label', 'placeholder', 'readonly', 'required', 'validator', 'default', 'empty_value', 'checked']

    #empty_value = None
    default = False
    validator = validators.is_bool
    checked = None

    def __init__(self, *args, **kwargs):

        if kwargs.has_key('checked'):
            self.checked = kwargs.pop('checked')

        super(Checkbox, self).__init__(*args, **kwargs)


class Radio(Checkbox):
    pass


class MultiCheckbox(MultiChoice):

    validator = validators.is_string
    checked = None

    
    def __init__(self, **kwargs):

        if kwargs.has_key('checked'):
            self.checked = kwargs.pop('checked')
        
        if not kwargs.has_key('choices'):
            kwargs['choices'] = []
        
        if kwargs.has_key('value'):

            if not isinstance(kwargs['value'], list) and not isinstance(kwargs['value'], tuple):
                kwargs['value'] = [kwargs['value']]
       
            for subvalue in kwargs['value']:
                kwargs['choices'].append(self.type.convert(subvalue, None, None))


        super(MultiCheckbox, self).__init__(**kwargs)

    
    def validate(self):

        for value in self.value:
            if value != '' and not value in self.choices:
                raise errors.ValidationError("'%s' is not an approved choice for %s.%s" % (self.value, self.prefix, self.name))


class IntegerMultiCheckbox(MultiCheckbox):

    validator = validators.is_integer


class Float(RenderableField):
    validator = validators.is_float


class RangedFloat(RangedInteger):
    validator = validators.is_float


class Keygen(RenderableField):
    
    challenge = None

    def __init__(self, *args, **kw):

        try:
            if flask.request.method == 'GET':
                app.logger.debug("Keygen new challenge")
                self.challenge = poobrains.helpers.random_string()
        except RuntimeError as e:
            pass

        super(Keygen, self).__init__(*args, **kw)


class File(RenderableField):

    validator = None
