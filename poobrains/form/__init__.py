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
    _controls = None

    name = None
    title = None
    method = None

    def __init__(self, name, title='', method='POST', action=None):
       
        self._fields = collections.OrderedDict()
        self._controls = helpers.CustomOrderedDict()

        self.name = name
        self.title = title
        self.method = method
        self.action = action


    def template_candidates(self, mode):
        
        tpls = []
        
        tpls.append('form-%s.jinja' % self.name)
        tpls.append('form.jinja')

        return tpls


    def render_fields(self):

        """
        Render fields of this form which have not yet been rendered.
        """

        rendered_fields = u''

        for field in self._fields.itervalues():
            if not field.rendered:
                rendered_fields += field.render()

        return rendered_fields


    def render_controls(self):

        """
        Render controls for this form.
        TODO: Do we *want* to filter out already rendered controls, like we do with fields?
        """

        rendered_controls = u''

        for control in self._controls.itervalues():
            rendered_controls += control.render()

        return rendered_controls


    def __getattr__(self, name):

        if self._fields.has_key(name):
            return self._fields[name]

        elif self._controls.has_key(name):
            return self._controls[name]

        raise AttributeError("Attribute not found: %s" % name)


    def __setattr__(self, name, value):

        if isinstance(value, fields.Field):
            self._fields[name] = value

        elif isinstance(value, Button):
            self._controls[name] = value

        else:
            super(Form, self).__setattr__(name, value)


    def __iter__(self):

        """
        Iterate over this forms fields. Yes, this comment is incredibly helpful.
        """

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
