# -*- coding: utf-8 -+-

# external imports
import flask

# parent imports
import poobrains
from poobrains import rendering
from poobrains import helpers

# internal imports
import fields


#class MetaForm(type):
#
#    def __new__(mcs, name, bases, attrs):
#
#        for attr_name, attr in attrs.iteritems():
#
#            if isinstance(attr, fields.Field) and not attr.name:
#                attr.name = attr_name
#
#        return type.__new__(mcs, name, bases, attrs)

class BaseForm(rendering.Renderable):

    fields = None
    controls = None
    
    name = None
    title = None

    def __new__(cls, *args, **kw):

        instance = super(BaseForm, cls).__new__(cls, *args, **kw)
        instance.fields = helpers.CustomOrderedDict()
        instance.controls = helpers.CustomOrderedDict()

        for attr_name in dir(instance):

            label_default = attr_name.capitalize()
            attr = getattr(instance, attr_name)

            if isinstance(attr, fields.Field):
                label = attr.label if attr.label else label_default
                field_clone = attr.__class__(name=attr_name, value=attr.value, label=attr.label, readonly=attr.readonly, validators=attr.validators)
                instance.fields[attr_name] = field_clone

            elif isinstance(attr, Fieldset):
                name = attr.name if attr.name else attr_name
                clone = attr.__class__(name=name, title=attr.title)
                instance.fields[attr_name] = clone

            elif isinstance(attr, Button):
                label = attr.label if attr.label else label_default
                button_clone = attr.__class__(attr.type, name=attr_name, value=attr.value, label=label)
                instance.controls[attr_name] = button_clone

        return instance
    
    
    def __init__(self, name=None, title=None):

        self.name = name if name else self.__class__.__name__.lower()

        if title:
            self.title = title
        elif not self.title: # Only use the fallback if title has been supplied neither to __init__ nor in class definition
            self.title = self.__class__.__name__


    def render_fields(self):

        """
        Render fields of this form which have not yet been rendered.
        """

        rendered_fields = u''

        for field in self.fields.itervalues():
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


#    def __getattribute__(self, name):
#
#        fields = super(BaseForm, self).__getattribute__('_fields')
#        controls = super(BaseForm, self).__getattribute__('_controls')
#
#        if fields.has_key(name):
#            return fields[name]
#
#        elif controls.has_key(name):
#            return controls[name]
#
#        return super(BaseForm, self).__getattribute__(name)
#
#
#    def __setattr__(self, name, value):
#
#        if isinstance(value, fields.Field) or isinstance(value, Fieldset):
#            self._fields[name] = value # what does this exactly do? call __gietattribute__('_fields') and then modify it?
#
#        elif isinstance(value, Button):
#            self._controls[name] = value # same question as above, just with '_controls'
#
#        else:
#            super(BaseForm, self).__setattr__(name, value)


    def __iter__(self):

        """
        Iterate over this forms fields. Yes, this comment is incredibly helpful.
        """
        return self.fields.itervalues()


class Form(BaseForm):

    method = None
    action = None

    def __init__(self, name=None, title=None, method=None, action=None):

        super(Form, self).__init__(name=name, title=title)
        self.method = method if method else 'POST'
        self.action = action if action else ''


    def template_candidates(self, mode):
        
        tpls = []
        
        tpls.append('form/form-%s.jinja' % self.name)
        tpls.append('form/form.jinja')

        return tpls


class Fieldset(BaseForm):

    rendered = None

    def __init__(self, *args, **kw):

        super(Fieldset, self).__init__(*args, **kw)
        self.rendered = False
    

    def template_candidates(self, mode):
        
        tpls = []
        
        tpls.append('form/fieldset-%s.jinja' % self.name)
        tpls.append('form/fieldset.jinja')

        return tpls
    

    def render(self, mode='full'):

        self.rrendered = True
        return super(Fieldset, self).render(mode)


class Button(rendering.Renderable):

    name = None
    type = None
    value = None
    label = None

    
    def __init__(self, type, name=None, value=None, label=None):

        super(Button, self).__init__()

        self.name = name
        self.type = type
        self.value = value
        self.label = label
