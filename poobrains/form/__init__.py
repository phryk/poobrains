# -*- coding: utf-8 -+-

# external imports
import functools
import flask

# parent imports
import poobrains

# internal imports
import fields


class BaseForm(poobrains.rendering.Renderable):

    fields = None
    controls = None
    
    name = 'None'
    title = None

    def __new__(cls, *args, **kw):

        instance = super(BaseForm, cls).__new__(cls, *args, **kw)
        instance.fields = poobrains.helpers.CustomOrderedDict()
        instance.controls = poobrains.helpers.CustomOrderedDict()
        instance.name = "yoink"
        for attr_name in dir(instance):

            label_default = attr_name.capitalize()
            attr = getattr(instance, attr_name)

            if isinstance(attr, fields.Field):
                label = attr.label if attr.label else label_default
                clone = attr.__class__(name=attr_name, value=attr.value, label=attr.label, readonly=attr.readonly, validators=attr.validators)
                #instance.fields[attr_name] = clone
                setattr(instance, attr_name, clone)

            elif isinstance(attr, Fieldset):
                name = attr.name if attr.name else attr_name
                clone = attr.__class__(name=name, title=attr.title)
                #instance.fields[attr_name] = clone
                setattr(instance, attr_name, clone)

            elif isinstance(attr, Button):
                label = attr.label if attr.label else label_default
                clone = attr.__class__(attr.type, name=attr_name, value=attr.value, label=label)
                instance.controls[attr_name] = clone

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


    def __setattr__(self, name, value):

        if isinstance(value, fields.Field):
            self.fields[name] = value

        elif isinstance(value, Button):
            self.controls[name] = value

        else:
            super(BaseForm, self).__setattr__(name, value)


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


    def handle(self, values):

        raise NotImplementedError("%s.handle not implemented." % self.__class__.__name__)


class AutoForm(Form):

    model = None
    instance = None

    def __init__(self, model_or_instance, mode='add', name=None, title=None, method=None, action=None):
    
        self.mode = mode

        if isinstance(model_or_instance, type(poobrains.storage.Model)):
            self.model = model_or_instance
            self.instance = self.model()

        else:
            self.instance = model_or_instance
            self.model = self.instance.__class__
            self.actions = self.instance.actions

        # TODO: Build fields

        if mode == 'delete':

            self.warning = fields.Message('deletion_irrevocable', value='Deletion is not revocable. Proceed?')
            self.submit = Button('submit', name='submit', value='delete', label='KILL')

        else:

            #poobrains.app.logger.debug('Iterating model fields.')
            for field in self.model._meta.get_fields():

                #poobrains.app.logger.debug(field)
                if isinstance(field, poobrains.storage.fields.Field):
                    form_field = field.form_class(field.name, value=getattr(self.instance, field.name), validators=field.form_extra_validators)
                    #self.fields[field.name] = form_field
                    setattr(self, field.name, form_field)

            self.controls['reset'] = Button('reset', label='Reset')
            self.controls['submit'] = Button('submit', name='submit', value='save', label='Save')


        name = name if name else '%s-%s' % (self.model.__name__.lower(), mode)
        super(AutoForm, self).__init__(name=name, title=title, method=method, action=action)


    def handle(self, values):

        poobrains.app.logger.debug("Form handle mode: %s." % self.mode)

        # handle POST for add and edit
        if self.mode in ('add', 'edit'):


            for field_name in self.model._meta.get_field_names():
                if not field_name in self.model.field_blacklist:
                    try:
                        setattr(self.instance, field_name, flask.request.form[field_name])
                    except Exception as e:
                        poobrains.app.logger.error("Possible bug in %s.handle." % self.__class__.__name__)
                        poobrains.app.logger.error("Affected field: %s.%s" % (self.model.__name__, field_name))

            try:
                self.instance.save()

            except peewee.IntegrityError as e:
                flask.flash('Integrity error: %s' % e.message, 'error')

                if mode == 'edit':
                    return flask.redirect(self.model.load(self.instance.id).url('edit'))

                return flask.redirect(self.model.url(mode='teaser-edit'))

            return flask.redirect(self.instance.url(mode='edit'))

        # Why the fuck does HTML not support DELETE!?
        elif self.mode == 'delete' and flask.request.method in ('POST', 'DELETE') and self.instance.id:
            message = "Deleted %s '%s'." % (self.model.__name__, self.instance.name)
            self.instance.delete_instance()
            flask.flash(message)

        return flask.redirect(self.model.url('teaser-edit'))


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


class Button(poobrains.rendering.Renderable):

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
