# -*- coding: utf-8 -+-

# external imports
import functools
import peewee
import werkzeug
import flask

# parent imports
import poobrains

# internal imports
import fields


class FormMeta(poobrains.helpers.MetaCompatibility, poobrains.helpers.ClassOrInstanceBound):
    pass

class BaseForm(poobrains.rendering.Renderable):

    __metaclass__ = FormMeta

    fields = None
    controls = None
    
    prefix = None
    name = 'None'
    title = None

    def __new__(cls, *args, **kw):

        instance = super(BaseForm, cls).__new__(cls, *args, **kw)
        instance.fields = poobrains.helpers.CustomOrderedDict()
        instance.controls = poobrains.helpers.CustomOrderedDict()
        
        for attr_name in dir(instance):

            label_default = attr_name.capitalize()
            attr = getattr(instance, attr_name)

            if isinstance(attr, fields.Field):
                label = attr.label if attr.label else label_default
                clone = attr.__class__(name=attr_name, value=attr.value, label=attr.label, readonly=attr.readonly, validators=attr.validators)
                #instance.fields[attr_name] = clone
                setattr(instance, attr_name, clone)

            elif isinstance(attr, Fieldset):
                clone = attr.__class__(name=attr_name, title=attr.title)
                #instance.fields[attr_name] = clone
                setattr(instance, attr_name, clone)

            elif isinstance(attr, Button):
                label = attr.label if attr.label else label_default
                clone = attr.__class__(attr.type, name=attr_name, value=attr.value, label=label)
                instance.controls[attr_name] = clone

        return instance
    
    
    def __init__(self, prefix=None, name=None, title=None):

        super(BaseForm, self).__init__()

        self.name = name if name else self.__class__.__name__.lower()

        if title:
            self.title = title
        elif not self.title: # Only use the fallback if title has been supplied neither to __init__ nor in class definition
            self.title = self.__class__.__name__

        self.prefix = prefix


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

        if isinstance(value, fields.Field) or isinstance(value, Fieldset):
            value.name = name
            value.prefix = "%s.%s" % (self.prefix, self.name) if self.prefix else self.name
            self.fields[name] = value

        elif isinstance(value, Button):
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


    def __getattr__(self, name):

        if self.fields.has_key(name):
            return self.fields[name]

        return super(BaseForm, self).__getattr__(name)


    def __iter__(self):

        """
        Iterate over this forms fields. Yes, this comment is incredibly helpful.
        """
        return self.fields.itervalues()
    
    
    @classmethod
    def templates(cls, mode=None):

        tpls = []

        for x in [cls] + cls.ancestors():

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


    def handle(self, values):

        poobrains.app.logger.error("base handle")
        for field in self.fields.itervalues():
            poobrains.app.logger.debug("field: %s" % field.name)
            if isinstance(field, Fieldset):
                try:
                    poobrains.app.logger.error("Calling handle for a Fieldset called %s." % field.name)
                    field.handle(values[field.name])
                except Exception as e:
                    poobrains.app.logger.error("Possible bug in %s.handle." % field.__class__.__name__)


class Form(BaseForm):

    method = None
    action = None

    def __init__(self, name=None, title=None, method=None, action=None):

        super(Form, self).__init__(name=name, title=title)
        self.method = method if method else 'POST'
        self.action = action if action else ''


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

            if hasattr(self.instance, 'actions'):
                self.actions = self.instance.actions


        if name:

            self.name = name
        else:

            if self.instance.id:
                self.name = "%s-%d-%s" % (self.model.__name__.lower(), self.instance.id, mode)
            else:
                self.name = "%s-%s" % (self.model.__name__.lower(), mode)


        if mode == 'delete':

            self.title = "Delete %s" % self.instance.name
            self.warning = fields.Message('deletion_irrevocable', value='Deletion is not revocable. Proceed?')
            self.submit = Button('submit', name='submit', value='submit', label='KILL')

        else:

            #poobrains.app.logger.debug('Iterating model fields.')
            for field in self.model._meta.get_fields():

                #poobrains.app.logger.debug(field)
                if isinstance(field, poobrains.storage.fields.Field) and field.name not in self.model.field_blacklist:
                    form_field = field.form_class(field.name, value=getattr(self.instance, field.name), validators=field.form_extra_validators)
                    #self.fields[field.name] = form_field
                    setattr(self, field.name, form_field)

            self.controls['reset'] = Button('reset', label='Reset')
            self.controls['submit'] = Button('submit', name='submit', value='submit', label='Save')


        #name = name if name else '%s-%s' % (self.model.__name__.lower(), mode)
        super(AutoForm, self).__init__(name=self.name, title=title, method=method, action=action)

        # override default title unless title was explicitly passed.
        if not title:

            self.title = "%s %s" % (self.mode.capitalize(), self.model.__name__)

            if self.instance.id:
                if hasattr(self.instance, 'title') and self.instance.title:
                    self.title = "%s '%s'" % (self.title, self.instance.title)
                elif self.instance.name:
                    self.title = "%s '%s'" % (self.title, self.instance.name)
                else:
                    self.title = "%s #%d" % (self.title, self.instance.id)

    def handle(self, values):

        # handle POST for add and edit
        if self.mode in ('add', 'edit'):
            for field_name in self.model._meta.get_field_names():
                if not field_name in self.model.field_blacklist:
                    try:
                        setattr(self.instance, field_name, values[field_name])
                    except werkzeug.exceptions.BadRequestKeyError:
                        poobrains.app.logger.error("Key '%s' missing in form data. Associated model is %s" % (field_name, self.model.__name__))
                        raise
                    except Exception as e:
                        poobrains.app.logger.error("Possible bug in %s.handle." % self.__class__.__name__)
                        poobrains.app.logger.error("Affected field: %s.%s" % (self.model.__name__, field_name))
                        poobrains.app.logger.debug(type(e))
                        poobrains.app.logger.debug(e)
                        poobrains.app.logger.debug(field_name)
                        poobrains.app.logger.debug(values)

            try:
                self.instance.save()

            except peewee.IntegrityError as e:
                flask.flash('Integrity error: %s' % e.message, 'error')

                if self.mode == 'edit':
                    return flask.redirect(self.model.load(self.instance.id).url('edit'))

                return flask.redirect(self.model.url(mode='teaser-edit'))
            
            super(AutoForm, self).handle(values) # calls .handle on all Fieldsets
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

        self.rendered = False
        super(Fieldset, self).__init__(*args, **kw)
    

    def render(self, mode=None):

        self.rendered = True
        return super(Fieldset, self).render(mode)


class AutoFieldset(AutoForm, Fieldset):

    rendered = None
   

    def render(self, mode=None):

        self.rendered = True
        return super(AutoForm, self).render(mode)


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
