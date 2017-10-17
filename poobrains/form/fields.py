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
from . import types


class BoundFieldMeta(poobrains.helpers.MetaCompatibility, poobrains.helpers.ClassOrInstanceBound):
    pass


class BaseField(object):

    __metaclass__ = poobrains.helpers.MetaCompatibility

    _created = None
    form = None # only filled if this is a field rendered outside of the form
    errors = None
    prefix = None
    name = None
    type = types.STRING
    value = None
    choices = None
    default = None # used when client sends no value for this field
    label = None
    multi = False # Whether this field takes multiple values (i.e. value passed to .bind will be a list)
    placeholder = None
    help_text = None
    readonly = None
    required = None
    validators = None


    class Meta:
        clone_props = ['name', 'type', 'multi', 'value', 'choices', 'label', 'placeholder', 'help_text', 'readonly', 'required', 'validators', 'default']


    def __new__(cls, *args, **kwargs):

        instance = super(BaseField, cls).__new__(cls, *args, **kwargs)
        instance._created = time.time()

        return instance


    def __init__(self, name=None, type=None, multi=None, value=None, choices=None, label=None, placeholder=None, help_text=None, readonly=False, required=False, validators=None, default=None, form=None, **kwargs):

        self.errors = []
        self.name = name
        self.label = label if label is not None else name
        self.placeholder = placeholder if placeholder else self.label
        self.help_text = help_text
        self.readonly = readonly
        self.required = required
        self.rendered = False

        if not type is None:
            self.type = type

        if not multi is None:
            self.multi = multi


        if not choices is None:
            self.choices = choices # leave choices of other __init__ intact. <- TODO: what other __init__? did i mean statically defined properties in subclasses?

        if callable(self.choices):
            self.choices = self.choices()


        if not default is None:
            self.default = default

        if self.default is None and self.multi:
            self.default = []

        if callable(self.default):
            self.default = self.default()


        if not value is None:
            self.value = value
        else:
            self.value = self.default


        if not validators is None:
            self.validators = validators
        else:
            self.validators = []

        if not form is None:

            self.form = form
            if self.form.prefix:
                self.prefix = "%s.%s" % (self.form.prefix, self.form.name)
            else:
                self.prefix = self.form.name
            self.form._add_external_field(self) # this has to be called *after* self.choices is filled


    def __getattr__(self, name):

        if name in ['label', 'placeholder']:

            real_value = super(BaseField, self).__getattr__(name)

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

    
    @property
    def ref_id(self):

        """ HTML 'id' attribute value"""

        if self.custom_id:
            return self.custom_id

        if self.prefix:
            return "%s-%s" % (self.prefix.replace('.', '-'), self.name)

        return self.name


    @property
    def list_id(self):

        """ HTML 'id' attribute for a datalist to be associated with this form element. """
        if self.choices:
            return "list-%s" % self.ref_id

        return False # no choices means no datalist


    @property
    def empty(self):

        return (self.multi and self.value == []) or self.value is None

    
    def checked(self, value):

        if self.multi:
            return value in self.value

        return value == self.value


    def validate(self):

        compound_error = errors.CompoundError()

        values = self.value if self.multi else [self.value]

        if not self.empty:

            for value in values:

                if self.choices and not value in [choice for choice, _ in self.choices]: # FIXME: I think this will fuck up when using optgroups
                    compound_error.append(errors.ValidationError("'%s' is not an approved choice for %s.%s" % (self.value, self.prefix, self.name)))

                else: # else because we don't want to clutter error output 
                    for validator in self.validators:
                        try:
                            validator(self.value)
                        except errors.ValidationError as e:
                            compound_error.append(e)

        elif self.required:
            compound_error.append(errors.ValidationError("Required field '%s' was left empty." % self.name))

        if len(compound_error):
            raise compound_error


    def bind(self, value):

        app.debugger.set_trace()

        compound_error = errors.CompoundError()

        empty = value == '' or (self.multi and value == []) # TODO: value in [[], ['']] if <input type="text" multiple> needs it!

        if empty:

            self.value = self.default

        else:

            if self.multi:

                self.value = [] # clear any already existing values
                for subvalue in value:

                    try:
                        self.value.append(self.type.convert(subvalue, None, None))

                    except errors.BadParameter:

                        e = errors.ValidationError("Invalid input '%s' for field %s.%s." % (value, self.prefix, self.name))
                        compound_error.append(e)
                        self.errors.append(e)

            else:

                try:
                    self.value = self.type.convert(value, None, None)

                except errors.BadParameter:

                    e = errors.ValidationError("Invalid input '%s' for field %s.%s." % (value, self.prefix, self.name))
                    compound_error.append(e)
                    self.errors.append(e)

        try:
            self.validate()

        except errors.CompoundError as ce:

            for e in ce:
                compound_error.append(e)
                self.errors.append(e)

        if len(compound_error):

            raise compound_error


    def value_string(self, value):

        """ Create a string representation of a (potential) field value for use in HTML """

        if value is None:
            return ''

        elif isinstance(value, bool):
            return 'true' if value == True else 'false'

        elif isinstance(value, datetime.datetime):
            return value.strftime('%Y-%m-%d %H:%M:%S')

        elif hasattr(value, 'handle_string'): # hacky check whether this is a Storable. Can't use isinstance because we can't depend on storage here (since storage depends on form )
            return value.handle_string

        else:
            return unicode(value)


class Value(BaseField):
    """ To put a static value into the form. """

    def validate(self):
        pass


    def bind(self, value):
        pass


class Field(BaseField, poobrains.rendering.Renderable):

    rendered = None

    def render(self):

        self.rendered = True
        return super(Field, self).render()


class Text(Field):
    pass


class Message(Field):

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.value)

    
    def validate(self):
        pass


    def bind(self, value):
        pass


class TextAutoComplete(Text):
    
    class Meta:
        clone_props = ['name', 'type', 'value', 'label', 'placeholder', 'readonly', 'required', 'validators', 'default', 'choices']


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


class Range(Field):

    min = None
    max = None
    type = types.INT


    def validate(self):

        super(RangedInteger, self).validate()

        if not self.empty:

            if self.value < self.min or self.value > self.max:
                raise errors.ValidationError("%s: %d is out of range. Must be in range from %d to %d." % (self.name, self.value, self.min, self.max))


class DateTime(Field):

    type = types.DATETIME


class Select(Field):

    empty_label = 'Please choose'
    
    class Meta:
        clone_props = Field._meta.clone_props + ['empty_label']


class Checkbox(Select):

    type = types.BOOL
    default = False


class Radio(Checkbox):
    pass


class MultiCheckbox(Select):

    multi = True
    
    def __init__(self, **kwargs):

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
            if value != '' and not value in [choice for choice, _ in self.choices]:
                raise errors.ValidationError("'%s' is not an approved choice for %s.%s" % (self.value, self.prefix, self.name))

            if callable(self.validator):
                self.validator(value)


class Keygen(Field):
    
    challenge = None

    def __init__(self, *args, **kw):

        try:
            if flask.request.method == 'GET':
                app.logger.debug("Keygen new challenge")
                self.challenge = poobrains.helpers.random_string()
        except RuntimeError as e:
            pass

        super(Keygen, self).__init__(*args, **kw)


class File(Field):
    pass
