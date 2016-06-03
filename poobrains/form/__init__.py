# -*- coding: utf-8 -+-

# external imports
import functools
import collections
import peewee
import werkzeug
import flask

# parent imports
import poobrains

# internal imports
import errors
import fields


class FormMeta(poobrains.helpers.MetaCompatibility, poobrains.helpers.ClassOrInstanceBound):
    pass


class BaseForm(poobrains.rendering.Renderable):

    __metaclass__ = FormMeta

    fields = None
    controls = None
    
    prefix = None
    name = None
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
                clone = attr.__class__(name=attr_name, value=attr.value, label=attr.label, readonly=attr.readonly, validator=attr.validator)
                instance.fields[attr_name] = clone
                #setattr(instance, attr_name, clone)

            elif isinstance(attr, Fieldset):
                clone = attr.__class__(name=attr_name, title=attr.title)
                instance.fields[attr_name] = clone
                #setattr(instance, attr_name, clone)

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


#    def __getattr__(self, name):
#
#        if self.fields.has_key(name):
#            return self.fields[name]
#
#        return super(BaseForm, self).__getattr__(name)


    def __iter__(self):

        """
        Iterate over this forms fields. Yes, this comment is incredibly helpful.
        """
        return self.fields.__iter__()
    
    
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


    def validate_and_bind(self, values):

        validation_messages = []
        binding_messages = []


        for k, field in self.fields.iteritems():
            if not values.has_key(field.name):
                if field.coercer != None and field.required:
                    validation_messages.append("Missing form input: %s.%s" % (field.prefix, field.name))
                break

            if isinstance(field, Fieldset):
                try:
                    field.validate_and_bind(values[field.name])
                except errors.ValidationError as e:
                    validation_messages.append(e.message)
                except ValueError: # happens when a coercer (.bind) fails
                    binding_messages.append("I don't understand %s for %s" % (value, field.name))

            else:

                try:
                    field.validate(values[field.name])
                    field.bind(values[field.name])
                except errors.ValidationError as e:
                    validation_messages.append(e.message)
                    field.value = values[field.name]
                except ValueError: # happens when a coercer (.bind) fails
                    binding_messages.append("I don't understand %s for %s" % (value, field.name))
                    field.value = values[field.name]

            #except:
            #    poobrains.app.logger.error("Possible bug in validate_and_bind or validator and coercer of %s not playing nice." % field.__class__)
            #    poobrains.app.logger.debug("Affected field: %s %s" % (field.__class__.__name__, field.name))
            #    raise


        if len(validation_messages):
            raise errors.ValidationError("Form was not validated. Errors were as follows:\n%s" % '\n\t'.join(validation_messages))

        if len(binding_messages):
            raise errors.BindingError("Can't make sense of some of your input.\n%s" % '\n\t'.join(binding_messages))



    def handle(self):

#        poobrains.app.logger.error("base handle")
#        for field in self.fields.itervalues():
#            poobrains.app.logger.debug("field: %s" % field.name)
#            if isinstance(field, Fieldset):
#                try:
#                    poobrains.app.logger.error("Calling handle for a Fieldset called %s." % field.name)
#                    field.handle(values[field.name])
#                except Exception as e:
#                    poobrains.app.logger.error("Possible bug in %s.handle." % field.__class__.__name__)

        raise NotImplementedError("%s.handle not implemented." % self.__class__.name__)


class Form(BaseForm):

    method = None
    action = None

    def __init__(self, name=None, title=None, method=None, action=None):

        super(Form, self).__init__(name=name, title=title)
        self.method = method if method else 'POST'
        self.action = action if action else ''

    def __setattr__(self, name, value):

        if self.name:
            if name == 'name' and not self.prefix:
                if flask.g.forms.has_key(self.name):
                    del(flask.g.forms[self.name])
                flask.g.forms[value] = self

            if name == 'prefix':
                if not value:
                    flask.g.forms[self.name] = self

                elif flask.g.forms.has_key(self.name):
                    del(flask.g.forms[self.name])

        super(Form, self).__setattr__(name, value)


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

        if mode == 'delete':

            self.title = "Delete %s" % self.instance.name
            self.warning = fields.Message('deletion_irrevocable', value='Deletion is not revocable. Proceed?')
            self.submit = Button('submit', name='submit', value='delete', label='KILL')

        else:

            #poobrains.app.logger.debug('Iterating model fields.')
            for field in self.model._meta.get_fields():

                #poobrains.app.logger.debug(field)
                if isinstance(field, poobrains.storage.fields.Field) and field.name not in self.model.field_blacklist:
                    form_field = field.form_class(field.name, value=getattr(self.instance, field.name))
                    self.fields[field.name] = form_field
                    #setattr(self, field.name, form_field)

            self.controls['reset'] = Button('reset', label='Reset')
            self.controls['submit'] = Button('submit', name='submit', value='submit', label='Save')

        if name:
            self.name = name
        else:

            if self.instance.id:
                self.name = "%s-%d-%s" % (self.model.__name__.lower(), self.instance.id, mode)
            else:
                self.name = "%s-%s" % (self.model.__name__.lower(), mode)

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


    def handle(self):

        # handle POST for add and edit
        if self.mode in ('add', 'edit'):
            for field_name in self.model._meta.get_field_names():
                if not field_name in self.model.field_blacklist:
                    setattr(self.instance, field_name, self.fields[field_name].value)

            try:
                self.instance.save()

            except peewee.IntegrityError as e:
                flask.flash('Integrity error: %s' % e.message, 'error')

                if self.mode == 'edit':
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

        self.rendered = False
        super(Fieldset, self).__init__(*args, **kw)
    

    def render(self, mode=None):

        self.rendered = True
        return super(Fieldset, self).render(mode)


    def validate(self, values):

        messages = []

        for field in self.fields.itervalues():
            try:
                field.validate(values[field.name])
            except errors.ValidationError as e:
                messages.append(e.message)

        if len(messages):
            raise errors.ValidationError("Fieldset %s could not be validated, errors below.\n%s" % (self.name, '\n\t'.join(messages)))


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
