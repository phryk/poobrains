# -*- coding: utf-8 -*-

import time # needed for ordered attributes
import datetime
import flask

# parent imports
#import poobrains
from poobrains import app
import poobrains.helpers
import poobrains.errors
import poobrains.rendering

# internal imports
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

        instance = super(BaseField, cls).__new__(cls, **kwargs)
        instance._created = time.time()

        return instance


    def __init__(self, name=None, type=None, multi=None, value=None, choices=None, label=None, placeholder=None, help_text=None, readonly=False, required=False, validators=None, default=None, form=None, **kwargs):

        self.errors = []
        self.name = name
        self.label = label or name
        self.placeholder = placeholder
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
            self.form._add_external_field(self) # NOTE: this has to be called *after* self.choices is filled


    def __setattr__(self, name, value):

        if name == 'name' and isinstance(value, basestring):
            assert not '.' in value, "Form Field names *must* not contain dots: %s" % value

        super(BaseField, self).__setattr__(name, value)


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

        compound_error = poobrains.errors.CompoundError()

        values = self.value if self.multi else [self.value]

        if not self.empty:

            for value in values:

                if self.choices and not value in [choice for choice, _ in self.choices]: # FIXME: I think this will fuck up when using optgroups
                    compound_error.append(poobrains.errors.ValidationError("'%s' is not an approved choice for %s.%s" % (self.value, self.prefix, self.name)))

                else: # else because we don't want to clutter error output 
                    for validator in self.validators:
                        try:
                            validator(self.value)
                        except poobrains.errors.ValidationError as e:
                            compound_error.append(e)

        elif self.required:
            compound_error.append(poobrains.errors.ValidationError("Required field '%s' was left empty." % self.name))

        if len(compound_error):
            raise compound_error


    def bind(self, value):

        compound_error = poobrains.errors.CompoundError()

        empty = value == '' or (self.multi and value == []) # TODO: value in [[], ['']] if <input type="text" multiple> needs it!

        if empty:

            self.value = self.default

        else:

            if self.multi:

                self.value = [] # clear any already existing values
                for subvalue in value:

                    try:
                        self.value.append(self.type.convert(subvalue, None, None))

                    except poobrains.errors.BadParameter:

                        e = poobrains.errors.ValidationError("Invalid input '%s' for field %s.%s." % (value, self.prefix, self.name))
                        compound_error.append(e)
                        self.errors.append(e)

            else:

                try:
                    self.value = self.type.convert(value, None, None)

                except poobrains.errors.BadParameter:

                    e = poobrains.errors.ValidationError("Invalid input '%s' for field %s.%s." % (value, self.prefix, self.name))
                    compound_error.append(e)
                    self.errors.append(e)

        try:
            self.validate()

        except poobrains.errors.CompoundError as ce:

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

    class Meta:
        abstract = True

    rendered = None

    def render(self):

        self.rendered = True
        return super(Field, self).render()


class Text(Field):

    class Meta:
        abstract = True


class Message(Field):

    class Meta:
        abstract = True

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.value)

    
    def validate(self):
        pass


    def bind(self, value):
        pass


class ObfuscatedText(Text):

    class Meta:
        abstract = True


class TextArea(Text):

    class Meta:
        abstract = True


class Range(Field):

    class Meta:
        abstract = True

    min = None
    max = None
    type = types.INT


    def __init__(self, min=0, max=100, **kwargs):

        super(Range, self).__init__(**kwargs)

        self.min = min
        self.max = max


    def validate(self):

        super(Range, self).validate()

        if not self.empty:

            if self.value < self.min or self.value > self.max:
                raise poobrains.errors.ValidationError("%s: %d is out of range. Must be in range from %d to %d." % (self.name, self.value, self.min, self.max))


class DateTime(Field):

    class Meta:
        abstract = True

    type = types.DATETIME


class Select(Field):

    empty_label = 'Please choose'
    
    class Meta:
        clone_props = Field._meta.clone_props + ['empty_label']


class Checkbox(Field):

    class Meta:
        abstract = True

    type = types.BOOL
    default = False

    def __init__(self, **kwargs):

        if kwargs.get('multi', False):

            if not kwargs.get('choices', False):
                kwargs['choices'] = [] # Checkbox must have choices. None passed is valid, because external Checkboxes

            if not kwargs.get('default', False):
                kwargs['default'] = []

        super(Checkbox, self).__init__(**kwargs)


    @property
    def type_bool(self):
        return self.type == types.BOOL


    def checked(self, value):

        if self.type == types.BOOL:
            return value == True

        return super(Checkbox, self).checked(value)


    def value_string(self, value):

        if self.type == types.BOOL:
            return 'true'

        return super(Checkbox, self).value_string(value)


class Radio(Field):

    class Meta:
        abstract = True
    
    def __init__(self, *args, **kwargs):

        assert not kwargs.get('multi', False), "Radios buttons can't have multiple values by definition."
        assert kwargs.get('choices', False), "Radio buttons need choices passed."
        super(Radio, self).__init__(**kwargs)


class Keygen(Field):

    class Meta:
        abstract = True
    
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

    class Meta:
        abstract = True
