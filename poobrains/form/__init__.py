# -*- coding: utf-8 -+-

# external imports
import time
import copy
import functools
import collections
import peewee
import werkzeug
import click
import flask

# parent imports
#import poobrains
from poobrains import app
import poobrains.errors
import poobrains.helpers
import poobrains.rendering


# internal imports
from . import fields
from . import types

class FormMeta(poobrains.helpers.MetaCompatibility, poobrains.helpers.ClassOrInstanceBound):

    def __new__(cls, name, bases, attrs):
        return super(FormMeta, cls).__new__(cls, name, bases, attrs)

    def __setattr__(cls, name, value):
        return super(FormMeta, cls).__setattr__(name, value)


class BaseForm(poobrains.rendering.Renderable):

    __metaclass__ = FormMeta

    class Meta:
        abstract = True

    _external_fields = None

    custom_id = None

    fields = None
    controls = None
    
    prefix = None
    name = None
    title = None

    def __new__(cls, *args, **kw):

        instance = super(BaseForm, cls).__new__(cls, *args, **kw)
        instance.fields = poobrains.helpers.CustomOrderedDict()
        instance.controls = poobrains.helpers.CustomOrderedDict()

        clone_attributes = []
        for attr_name in dir(instance):

            attr = getattr(instance, attr_name)
            if isinstance(attr, fields.BaseField) or isinstance(attr, Fieldset) or isinstance(attr, Button): # FIXME: This should be doable with just one check
                clone_attributes.append((attr_name, attr))

        for (attr_name, attr) in sorted(clone_attributes, key=lambda x: getattr(x[1], '_created')): # Get elements in the same order they were defined in, as noted by _created property

                kw = {}
                for propname in attr._meta.clone_props:

                    value = getattr(attr, propname)
                    if not callable(value):
                        value = copy.deepcopy(value)
                    kw[propname] = value

                kw['name'] = attr_name

                clone = attr.__class__(**kw)
                setattr(instance, attr_name, clone)

        return instance
    
    
    def __init__(self, prefix=None, name=None, title=None, custom_id=None):

        self._external_fields = []
        super(BaseForm, self).__init__()
        self.name = name if name else self.__class__.__name__

        if title:
            self.title = title
        elif not self.title: # Only use the fallback if title has been supplied neither to __init__ nor in class definition
            self.title = self.__class__.__name__

        self.prefix = prefix
        self.custom_id = custom_id

    
    def __setattr__(self, name, value):

        if isinstance(value, fields.BaseField) or isinstance(value, Fieldset):
            value.name = name
            value.prefix = "%s.%s" % (self.prefix, self.name) if self.prefix else self.name
            self.fields[name] = value

        elif isinstance(value, Button):
            value.name = name
            value.prefix = "%s.%s" % (self.prefix, self.name) if self.prefix else self.name
            self.controls[name] = value

        elif name == 'prefix':
            super(BaseForm, self).__setattr__(name, value)
            if value:
                child_prefix = "%s.%s" % (value, self.name)
            else:
                child_prefix = self.name

            for field in self.fields.itervalues():
                field.prefix = child_prefix

            for button in self.controls.itervalues():
                button.prefix = child_prefix

        else:
            super(BaseForm, self).__setattr__(name, value)


    def __iter__(self):

        """
        Iterate over this forms renderable fields.
        """

        for field in self.fields.itervalues():
            if isinstance(field, (fields.Field, Fieldset)) and field.name not in self._external_fields:
                yield field

    
    def _add_external_field(self, field):

        """
        Add a field which is to be rendered outside of this form, but processed by it.
        Fields like this can be created by passing a Form object to the Field constructor.
        """

        if isinstance(field, fields.Checkbox) and self.fields.has_key(field.name) and type(field) == type(self.fields[field.name]): # checkboxes/radio inputs can pop up multiple times, but belong to the same name
            self.fields[field.name].choices.extend(field.choices)

        else:
            if self.prefix:
                field.prefix = "%s.%s" % (self.prefix, self.name)
            else:
                field.prefix = self.name

            self.fields[field.name] = field

        self._external_fields.append(field.name)


    @property
    def renderable_fields(self):

        return [field for field in self] 


    @property
    def fieldsets(self):

        return [field for field in self if isinstance(field, Fieldset)]


    @property
    def ref_id(self):

        """ HTML 'id' attribute (to enable assigning fields outside that <form> element). """

        if self.custom_id:
            return self.custom_id

        if self.prefix:
            return "%s-%s" % (self.prefix.replace('.', '-'), self.name)

        return self.name


    def empty(self): # TODO: find out why I didn't make this @property
        for field in self:
            if not field.empty:
                return False
        return True


    @property
    def readonly(self):

        for field in self:
            if not field.readonly:
                return False

        return True


    def bind(self, values, files):

        if not values is None:
            compound_error = poobrains.errors.CompoundError()

            actionable_fields = [f for f in self]
            actionable_fields += [self.fields[name] for name in self._external_fields]

            for field in actionable_fields:

                if not field.readonly:
                    
                    source = files if isinstance(field, fields.File) else values
                    if not source.has_key(field.name):

                        if field.multi or isinstance(field, Fieldset):
                            field_values = werkzeug.datastructures.MultiDict()
                        elif field.type == types.BOOL:
                            field_values = False # boolean values via checkbox can only ever be implied false. yay html!
                        else:
                            field_values = ''

                    elif field.multi:
                        field_values = source.getlist(field.name)
                    else:
                        field_values = source[field.name]

                    try:
                        if isinstance(field, Fieldset):
                            sub_files = files[field.name] if files.has_key(field.name) else werkzeug.datastructures.MultiDict()
                            field.bind(field_values, sub_files)
                        else:
                            field.bind(field_values)

                    except poobrains.errors.CompoundError as ce:

                        for e in ce.errors:
                            compound_error.append(e)

            for name, control in self.controls.iteritems():
                if isinstance(control, Button):
                    control.value = values.get(name, False)

            if len(compound_error):
                raise compound_error


    def render_fields(self):

        """
        Render fields of this form which have not yet been rendered.
        """

        rendered_fields = u''

        for field in self:
            if not field.rendered:
                rendered_fields += field.render()

        return rendered_fields


    def render_controls(self):

        """
        Render controls for this form.
        TODO: Do we *want* to filter out already rendered controls, like we do with fields?
        """

        rendered_controls = u''

        for control in self.controls.itervalues():
            rendered_controls += control.render()

        return rendered_controls


    def templates(self, mode=None):

        tpls = []

        for x in [self.__class__] + self.__class__.ancestors():

            name = x.__name__.lower()

            if issubclass(x, BaseForm):
                tpls.append('form/%s.jinja' % name)
                
                if mode:
                    tpls.append('form/%s-%s.jinja' % (name, mode))

            else:
                tpls.append('%s.jinja' % name)

                if mode:
                    tpls.append('%s-%s.jinja' % (name, mode))

        return tpls


    def process(self, submit):

        raise NotImplementedError("%s.process not implemented." % self.__class__.__name__)


class Form(BaseForm):

    method = None
    action = None

    class Meta:
        abstract = True

    def __init__(self, prefix=None, name=None, title=None, method=None, action=None, custom_id=None, **kwargs):

        super(Form, self).__init__(prefix=prefix, name=name, title=title, custom_id=custom_id)
        self.method = method if method else 'POST'
        self.action = action if action else ''


    @classmethod
    def class_view(cls, mode='full', **kwargs):

        instance = cls(**kwargs)
        return instance.view(mode)


    def validate(self):
        pass


    @poobrains.helpers.themed
    def view(self, mode='full', **kwargs):

        """
        view function to be called in a flask request context
        """

        if flask.request.method == self.method:

            validation_error = None
            binding_error = None
            values = flask.request.form.get(self.name, werkzeug.datastructures.MultiDict())
            files = flask.request.files.get(self.name, werkzeug.datastructures.FileMultiDict())

            try:
                self.bind(values, files)
                self.validate()

                try:
                    return self.process(flask.request.form['submit'][len(self.ref_id)+1:])

                except poobrains.errors.CompoundError as e:
                    for error in e.errors:
                        flask.flash(error.message, 'error')

            except poobrains.errors.CompoundError as e:
                for error in e.errors:
                    flask.flash(error.message, 'error')

            except poobrains.errors.ValidationError as e:
                flask.flash(e.message, 'error')

                if e.field:
                    self.fields[e.field].append(e)


            if not flask.request.form['submit'].startswith(self.ref_id): # means the right form was submitted, should be implied by the path tho…
                app.logger.error("Form %s: submit button of another form used: %s" % (self.name, flask.request.form['submit']))
                flask.flash("The form you just used might be broken. Bug someone if this problem persists.", 'error')

        return self




class Fieldset(BaseForm):

    errors = None
    readonly = None
    rendered = None
    multi = False
    _default = werkzeug.MultiDict()

    class Meta:
        abstract = True
        clone_props = ['name', 'title']

    
    def __new__(cls, *args, **kwargs):

        instance = super(Fieldset, cls).__new__(cls, *args, **kwargs)
        instance._created = time.time()

        return instance


    def __init__(self, *args, **kw):

        self.rendered = False
        self.readonly = False
        self.errors = []
        super(Fieldset, self).__init__(*args, **kw)
    

    def render(self, mode=None):

        self.rendered = True
        return super(Fieldset, self).render(mode)


    def process(self, submit):

        raise NotImplementedError("%s.process not implemented." % self.__class__.__name__)


    def __setattr__(self, name, value):

        if name == 'value':
            for field in self.fields.itervalues():
                if hasattr(value, field.name):
                    field.value = getattr(value, field.name)
        else:
            super(Fieldset, self).__setattr__(name, value)


class Button(poobrains.rendering.Renderable):

    name = None
    type = None
    value = None
    label = None

    class Meta:
        clone_props = ['type', 'name', 'value', 'label']
    
    
    def __new__(cls, *args, **kwargs):

        instance = super(Button, cls).__new__(cls, *args, **kwargs)
        instance._created = time.time()

        return instance


    def __init__(self, type, name=None, value=None, label=None):

        super(Button, self).__init__()

        self.name = name
        self.type = type
        self.value = value
        self.label = label


    def templates(self, mode=None):

        return ['form/button-%s.jinja' % self.type, 'form/button.jinja']
