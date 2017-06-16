# -*- coding: utf-8 -*-

import time # needed for ordered attributes
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

    _created = None
    _empty = None # hint if value of this field was set to empty_value <- TODO: is this even used anymore? don't we just have .empty()?
    form = None # only filled if this is a field rendered outside of the form
    errors = None
    prefix = None
    name = None
    value = None
    empty_value = '' # value which is considered to be "empty"
    default = None # used when client sends no value for this field
    label = None
    multi = False # Whether this field takes multiple values (i.e. value passed to .bind will be a list)
    placeholder = None
    readonly = None
    required = None
    validator = validators.is_string
    coercer = coercers.coerce_string

    class Meta:
        clone_props = ['name', 'value', 'label', 'placeholder', 'readonly', 'required', 'validator', 'default']


    def __new__(cls, *args, **kwargs):

        instance = super(Field, cls).__new__(cls, *args, **kwargs)
        instance._created = time.time()

        return instance

    def __init__(self, name=None, value=None, label=None, placeholder=None, readonly=False, required=False, validator=None, default=None, form=None, **kwargs):

        self.errors = []
        self.name = name
        self.value = value
        self.label = label if label is not None else name
        self.placeholder = placeholder if placeholder else self.label
        self.readonly = readonly
        self.required = required
        self.rendered = False
        if not default is None:
            self.default = default
        
        if validator:
            self.validator = validator

        
        if form is not None:
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
        return self.value == self.empty_value

    
    def validate(self):

        if not self.validator:
            return

        if not self.empty():
            self.validator(self.value)

        elif self.required:
            raise errors.ValidationError("Required field '%s' was left empty." % self.name)


    def coerce(self, value):

        if not self.coercer:
            return value

        if not value is None:
            return self.coercer(value)
        return None

    
    def bind(self, value):

        if isinstance(value, errors.MissingValue):
            self.value = self._default

        else:
            try:
                self.value = self.coerce(value)

                #if self.required and self.empty():
                if self.empty():
                    self.value = self._default


            except ValueError:
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
        return self.coerce(self.default() if callable(self.default) else self.default)



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
            self.choices = []
        else:
            self.choices = choices


class ObfuscatedText(Text):
    pass


class TextArea(Text):
    pass


class Integer(RenderableField):
    default = 0
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

    choices = None
    empty_label = 'Please choose'
    multi = None
    
    class Meta:
        clone_props = ['name', 'value', 'label', 'placeholder', 'readonly', 'required', 'validator', 'default', 'choices', 'empty_label', 'multi']
    
    def __init__(self, choices=None, multi=False, **kwargs):

        if not choices is None:
            self.choices = choices
        else:
            self.choices = []

        self.multi = multi

        super(Choice, self).__init__(**kwargs)


    def validate(self):

        choices = self.choices() if callable(self.choices) else self.choices
        if not self.value in dict(choices).keys(): # FIXME: I think this will fuck up, at least for optgroups
            raise errors.ValidationError("'%s' is not an approved choice for %s.%s" % (self.value, self.prefix, self.name))


class MultiChoice(Choice):

    multi = True
    default = []
    empty_value = []

    def __init__(self, *args, **kwargs):
        super(MultiChoice, self).__init__(*args, **kwargs)

        if self.value is None:
            self.value = []

    
    def empty(self):

        if self.value == self.empty_value or len(self.value) == 0:
            return True

        for value in self.value:
            if value != '':
                if self.coercer:
                    try:
                        self.coercer(value)
                        return False
                    
                    except ValueError:
                        pass

        return True # default to True if no coercible non-'' values where found


    def validate(self):
        
        for value in self.value:
            if value != '' and not value in dict(self.choices).keys(): # FIXME: I think this will fuck up, at least for optgroups
                raise errors.ValidationError("'%s' is not an approved choice for %s.%s" % (self.value, self.prefix, self.name))


    def coerce(self, values):
        
        error = errors.CompoundError()

        if not isinstance(values, list):
            values = [values]

        if not self.coercer:
            return values

        coerced = []
        for value in values:

            try:
                coerced.append(self.coercer(value))

            except ValueError:
                e = errors.ValidationError("Invalid input '%s' for field %s." % (value, self.name))
                self.errors.append(e)
                error.append(e)

        if len(error):
            raise error

        return coerced


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


class ForeignKeyChoice(TextAutoComplete):

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


    def validate(self):
        
        if not self.value is None:
            if not isinstance(self.value, self.storable):
                raise errors.ValidationError("Unknown %s handle '%s'." % (self.storable.__name__, self.value))
        elif self.required:
            raise errors.ValidationError("Field %s is required." % self.name)

    
    def coerce(self, value):
        if not value is None:
            try:
                return self.storable.load(self.coercer(value))
            except self.storable.DoesNotExist as e:
                self.errors.append(e)
        return None


class Checkbox(RenderableField):

    class Meta:
        clone_props = ['name', 'value', 'label', 'placeholder', 'readonly', 'required', 'validator', 'default', 'empty_value', 'checked']

    empty_value = None
    default = False
    coercer = coercers.coerce_bool
    validator = validators.is_bool
    checked = None

    def __init__(self, *args, **kwargs):

        if kwargs.has_key('checked'):
            self.checked = kwargs.pop('checked')

        super(Checkbox, self).__init__(*args, **kwargs)


class Radio(Checkbox):
    pass


class MultiCheckbox(MultiChoice):

    coercers = coercers.coerce_string
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
                #kwargs['choices'].append(coercers.coerce_string(None, subvalue))
                kwargs['choices'].append(self.coercer(subvalue))
                #kwargs['choices'].append(subvalue)

        super(MultiCheckbox, self).__init__(**kwargs)

    
    def validate(self):

        for value in self.value:
            if value != '' and not value in self.choices:
                raise errors.ValidationError("'%s' is not an approved choice for %s.%s" % (self.value, self.prefix, self.name))


class IntegerMultiCheckbox(MultiCheckbox):

    coercer = coercers.coerce_int
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
                poobrains.app.logger.debug("Keygen new challenge")
                self.challenge = helpers.random_string()
        except RuntimeError as e:
            pass

        super(Keygen, self).__init__(*args, **kw)


class File(RenderableField):

    validator = None
    coercer = None
