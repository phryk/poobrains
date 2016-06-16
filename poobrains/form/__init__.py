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

    errors = None
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
        self.errors = []
        self.name = name if name else self.__class__.__name__

        if title:
            self.title = title
        elif not self.title: # Only use the fallback if title has been supplied neither to __init__ nor in class definition
            self.title = self.__class__.__name__

        self.prefix = prefix


    def empty(self):
        for field in self:
            if not field.empty():
                return False
        return True
    
    
    def validate(self, values):

        compound_error = errors.CompoundError()

        for field in self:

            try:
                field_values = values[field.name]

                try:
                    field.validate(field_values)
                except errors.ValidationError as e:
                    compound_error.append(e)


            except werkzeug.exceptions.BadRequestKeyError as e:

                if isinstance(field, Fieldset):

                    poobrains.app.logger.error('All data for fieldset %s.%s missing.' % (field.prefix, field.name))
                    poobrains.app.debugger.set_trace()
                    raise # da woof!

                else:

                    try:
                        field.validate(field.missing_value)

                    except errors.ValidationError as e:
                        compound_error.append(e)

        if len(compound_error):
            raise compound_error


    def bind(self, values):

        compound_error = errors.CompoundError()

        for field in self: # magic iteration skipping type fields.Value
            
            try:
                field_values = values[field.name]
            
                try:
                    field.bind(values[field.name])
                #except errors.BindingError as e
                except ValueError as e:
                    compound_error.append(e)

            except werkzeug.exceptions.BadRequestKeyError as e:

                if isinstance(field, Fieldset):
                    raise
                else:
                    field.value = field.missing_value # because no value is a negative value, according to html form behavior :F


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
        Iterate over this forms fields except ValueFields.
        Yes, this is incredibly helpful.
        """

        for k in self.fields.keys():
            if not isinstance(self.fields[k], fields.Value):
                yield self.fields[k]
    
    
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

        raise NotImplementedError("%s.handle not implemented." % self.__class__.__name__)


class Form(BaseForm):

    method = None
    action = None

    def __init__(self, prefix=None, name=None, title=None, method=None, action=None):

        super(Form, self).__init__(prefix=prefix, name=name, title=title)
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


    def view(self, mode=None):

        """
        view function to be called in a flask request context
        """

        if flask.request.method == self.method:
        
            values = flask.request.form[self.name]

            try:
                self.validate(values)

            except errors.CompoundError as e:
                for error in e.errors:
                    flask.flash(error.message, 'error')

            try:
                self.bind(values)

            except errors.CompoundError as e:
                for error in e.errors:
                    flask.flash(error.message, 'error')

        return self


class BoundForm(Form):

    mode = None
    model = None
    instance = None
    
    def __new__(cls, model_or_instance, mode=None, prefix=None, name=None, title=None, method=None, action=None):
    
        f = super(BoundForm, cls).__new__(cls, prefix=prefix, name=name, title=title, method=method, action=action)

        if isinstance(model_or_instance, type(poobrains.storage.Model)): # hacky
            f.model = model_or_instance
            f.instance = f.model()

        else:
            f.instance = model_or_instance
            f.model = f.instance.__class__

        if hasattr(f.instance, 'actions'):
            f.actions = f.instance.actions

        return f
    
    
    def __init__(self, model_or_instance, mode=None, prefix=None, name=None, title=None, method=None, action=None):
        super(BoundForm, self).__init__(prefix=prefix, name=name, title=title, method=method, action=action)
        self.mode = mode


# TODO: Actually split AutoForm
class AddForm(BoundForm):

    def __new__(cls, model_or_instance, mode='add', prefix=None, name=None, title=None, method=None, action=None):
        
        f = super(AddForm, cls).__new__(cls, model_or_instance, prefix=prefix, name=name, title=title, method=method, action=action)

        for field in f.model._meta.sorted_fields:

            if field.name not in f.model.form_blacklist:

                if isinstance(field, poobrains.storage.fields.ForeignKeyField):
                    #TODO: is this the place to do permission checking for the field?

                    choices = []
                    for choice in field.rel_model.select():
                        if hasattr(choice, 'name') and choice.name:
                            choice_name = choice.name
                        else:
                            choice_name = "%s #%d" % (choice.__class__.__name__, choice.id)
                        choices.append((choice.id, choice_name))

                    form_field = field.form_class(field.name, choices=choices)
                    #f.fields[field.name] = form_field
                    setattr(f, field.name, form_field)

                elif isinstance(field, poobrains.storage.fields.Field):

                    if issubclass(field.form_class, fields.Choice):
                        form_field = field.form_class(field.name, choices=field.choices)
                    else:
                        form_field = field.form_class(field.name)

                    #f.fields[field.name] = form_field
                    setattr(f, field.name, form_field)

            f.controls['reset'] = Button('reset', label='Reset')
            f.controls['submit'] = Button('submit', name='submit', value='submit', label='Save')

        return f

    
    def __init__(self, model_or_instance, mode='add', prefix=None, name=None, title=None, method=None, action=None):
        
        if not name:
            name = self.instance.id_string
    
        super(AddForm, self).__init__(model_or_instance, mode=mode, prefix=prefix, name=name, title=title, method=method, action=action)

        if not title:
    
            if hasattr(self.instance, 'title') and self.instance.title:
                self.title = "%s %s '%s'" % (self.mode, self.model.__name__, self.instance.title)
            elif self.instance.name:
                self.title = "%s %s '%s'" % (self.mode, self.model.__name__, self.instance.name)
            elif self.instance.id:
                self.title = "%s %s #%d" % (self.mode, self.model.__name__, self.instance.id)
            elif self.instance._get_pk_value():
                self.title = "%s %s '%s'" % (self.mode, self.model.__name__, self.instance._get_pk_value())
            else:
                self.title = "%s %s" % (self.mode, self.model.__name__)

        for name, field in self.fields.iteritems():
            if hasattr(self.instance, name) and getattr(self.instance, name):
                field.value = getattr(self.instance, name)
 

    def handle(self):

        for field in self.model._meta.sorted_fields:
            if not field.name in self.model.form_blacklist:
                if isinstance(getattr(self.model, field.name), poobrains.storage.fields.ForeignKeyField):
                    try:
                        setattr(self.instance, field.name, field.rel_model.load(self.fields[field.name].value))
                    except field.rel_model.DoesNotExist:
                        flask.flash("%s instance %s does not exist anymore." % (field.rel_model.__name__, self.fields[field.name].value))
                        flask.flash(field.rel_model)
                        flask.flash(self.fields[field.name].value)
                else:
                    setattr(self.instance, field.name, self.fields[field.name].value)

        try:

            if self.mode == 'add':
                saved = self.instance.save(force_insert=True) # To make sure Administerables with CompositeKey as primary get inserted properly
            else:
                saved = self.instance.save()

            if saved:
                flask.flash("Saved %s %s." % (self.model.__name__, self.instance.id_string))
                try:
                    return flask.redirect(self.instance.url('edit'))
                except LookupError:
                    return self
            else:
                flask.flash("Couldn't save %s." % self.model.__name__)

        except peewee.IntegrityError as e:
            flask.flash('Integrity error: %s' % e.message, 'error')

        return self


class EditForm(AddForm):
    
    def __new__(cls, model_or_instance, mode='edit', prefix=None, name=None, title=None, method=None, action=None):
        return super(EditForm, cls).__new__(cls, model_or_instance, mode=mode, prefix=prefix, name=name, title=title, method=method, action=action)
   

    def __init__(self, model_or_instance, mode='edit', prefix=None, name=None, title=None, method=None, action=None):
        super(EditForm, self).__init__(model_or_instance, mode=mode, prefix=prefix, name=name, title=title, method=method, action=action)



class DeleteForm(BoundForm):

    def __new__(cls, model_or_instance, mode='delete', prefix=None, name=None, title=None, method=None, action=None):
        
        f = super(DeleteForm, cls).__new__(cls, model_or_instance, prefix=prefix, name=None, title=title, method=method, action=action)

        f.title = "Delete %s" % f.instance.name
        f.warning = fields.Message('deletion_irrevocable', value='Deletion is not revocable. Proceed?')
        f.submit = Button('submit', name='submit', value='delete', label='KILL')

        return f


    def __init__(self, model_or_instance, mode='delete', prefix=None, name=None, title=None, method=None, action=None):
        super(DeleteForm, self).__init__(model_or_instance, mode=mode, prefix=prefix, name=self.name, title=title, method=method, action=action)
        if not title:
            if hasattr(self.instance, 'title') and self.instance.title:
                self.title = "Delete %s %s" % (self.model.__name__, self.instance.title)
            else:
                self.title = "Delete %s %s" % (self.model.__name__, unicode(self.instance._get_pk_value()))

    
    def handle(self):

        if hasattr(self.instance, 'title') and self.instance.title:
            message = "Deleted %s '%s'." % (self.model.__name__, self.instance.title)
        else:
            message = "Deleted %s '%s'." % (self.model.__name__, unicode(self.instance._get_pk_value()))
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


    def __setattr__(self, name, value):

        if name == 'value':
            print "FIELDSET VALUE"
            for field in self.fields.itervalues():
                if hasattr(value, field.name):
                    field.value = getattr(value, field.name)
        else:
            super(Fieldset, self).__setattr__(name, value)


class AddFieldset(AddForm, Fieldset):

    rendered = None


    def __new__(cls, *args, **kwargs):

        f = super(AddFieldset, cls).__new__(cls, *args, **kwargs)
        f.controls.clear()

        return f
    

    def render(self, mode=None):

        self.rendered = True
        return super(AddFieldset, self).render(mode)


class EditFieldset(EditForm, Fieldset):

    rendered = None
 
    def render(self, mode=None):

        self.rendered = True
        return super(EditFieldset, self).render(mode)


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
