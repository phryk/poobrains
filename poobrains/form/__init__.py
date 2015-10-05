# -*- coding: utf-8 -+-

# external imports
import flask
import collections

# parent imports
from poobrains import rendering
from poobrains import helpers

# internal imports
import fields

class Form(rendering.Renderable):
    
    _fields = None
    _rendered = None

    name = None
    title = None
    method = None
    controls = None

    def __init__(self, name, title='', method='POST', action=None, tpls=None):
       
        self.name = name
        self.title = title
        self.method = method
        self.action = action
        self._fields = collections.OrderedDict()
        self.controls = helpers.CustomOrderedDict()

        self.tpls = []
        if tpls:
            self.tpls += tpls
        
        self.tpls.append('form-%s.jinja' % self.name)
        self.tpls.append('form.jinja')

        self.render_reset()


    def template_candidates(self, mode):
        return self.tpls


    #def add_field(self, name, field_type, value=None):
    #    self.fields[name] = (field_type, value)


    def add_button(self, type, name=None, value=None, label=None):

        self.controls[name] = Button(type, name=name, value=value, label=label)


    def render_reset(self):
        self._rendered = []


    def render_field(self, name):
        
        field_type, value = self.fields[name]

        tpls = ["fields/%s.jinja" % (field_type,)]
        tpls.append("fields/field.jinja")

        self._rendered.append(name)
        return flask.render_template(tpls, field_type=field_type, name=name, value=value)


    def render_fields(self):
        
        rendered_fields = u''

        for name in self.fields.keys():

            if name not in self._rendered:
                rendered_fields += self.render_field(name)

        return rendered_fields


    def __getattr__(self, name):

        if self._fields.has_key(name):
            return self._fields[name]

        raise AttributeError("Attribute not found: %s" % name)

    def __setattr__(self, name, value):

        if isinstance(value, fields.Field):
            self._fields[name] = value

        else:
            super(Form, self).__setattr__(name, value)


    def __iter__(self):
        #return self._fields.__iter__()
        return self._fields.itervalues()


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