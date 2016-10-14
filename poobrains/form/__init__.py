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

    class Meta:
        abstract = True

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

#            label_default = attr_name.capitalize()
#            attr = getattr(instance, attr_name)
#
#            if isinstance(attr, fields.Field):
#                label = attr.label if attr.label else label_default
#                clone = attr.__class__(name=attr_name, value=attr.value, label=attr.label, readonly=attr.readonly, validator=attr.validator)
#                #instance.fields[attr_name] = clone
#                setattr(instance, attr_name, clone)
#
#            elif isinstance(attr, Fieldset):
#                clone = attr.__class__(name=attr_name, title=attr.title)
#                #instance.fields[attr_name] = clone
#                setattr(instance, attr_name, clone)
#
#            elif isinstance(attr, Button):
#                label = attr.label if attr.label else label_default
#                clone = attr.__class__(attr.type, name=attr_name, value=attr.value, label=label)
#                instance.controls[attr_name] = clone

            attr = getattr(instance, attr_name)
            if isinstance(attr, fields.Field) or isinstance(attr, Fieldset) or isinstance(attr, Button): # FIXME: This should be doable with just one check

                kw = {}
                for propname in attr._meta.clone_props:
                    kw[propname] = getattr(attr, propname)
                
                clone = attr.__class__(**kw)
                setattr(instance, attr_name, clone)

        return instance
    
    
    def __init__(self, prefix=None, name=None, title=None):
        
        super(BaseForm, self).__init__()
        self.name = name if name else self.__class__.__name__

        if title:
            self.title = title
        elif not self.title: # Only use the fallback if title has been supplied neither to __init__ nor in class definition
            self.title = self.__class__.__name__

        self.prefix = prefix

    
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
        Iterate over this forms renderable fields.
        """

        for field in self.fields.itervalues():
            if isinstance(field, (fields.RenderableField, Fieldset)):
                yield field


    @property
    def renderable_fields(self):

        return [field for field in self] 


    def empty(self):
        for field in self:
            if not field.empty():
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
            compound_error = errors.CompoundError()

            for field in self: # magic iteration yielding only renderable fields

                if not field.readonly:
                    
                    source = files if isinstance(field, fields.File) else values
                    if source.has_key(field.name):
                        field_values = source[field.name]
                    else:
                        #field_values = errors.MissingValue()
                        field_values = field._default
                    
                    try:
                        field.bind(field_values)
                    except errors.ValidationError as e:
                        compound_error.append(e)

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

    class Meta:
        abstract = True

    def __init__(self, prefix=None, name=None, title=None, method=None, action=None):

        super(Form, self).__init__(prefix=prefix, name=name, title=title)
        self.method = method if method else 'POST'
        self.action = action if action else ''

#    def __setattr__(self, name, value):
#
#        if self.name:
#            if name == 'name' and not self.prefix:
#                if flask.g.forms.has_key(self.name):
#                    del(flask.g.forms[self.name])
#                flask.g.forms[value] = self
#
#            if name == 'prefix':
#                if not value:
#                    flask.g.forms[self.name] = self
#
#                elif flask.g.forms.has_key(self.name):
#                    del(flask.g.forms[self.name])
#
#        super(Form, self).__setattr__(name, value)


    @classmethod
    def class_view(cls, mode='full', *args, **kwargs):

        instance = cls(*args, **kwargs)
        return instance.view(mode)


    @poobrains.helpers.themed
    def view(self, mode='full', *args, **kwargs):

        """
        view function to be called in a flask request context
        """
        if flask.request.method == self.method:

            validation_error = None
            binding_error = None
            values = flask.request.form[self.name]
            files = flask.request.files[self.name] if flask.request.files.has_key(self.name) else werkzeug.datastructures.FileMultiDict()
            #FIXME: filter self.readonly in here instead of .bind and .handle?
            try:
                self.bind(values, files)

                try:
                    return self.handle()

                except errors.CompoundError as handling_error:
                    for error in handling_error.errors:
                        flask.flash(error.message, 'error')

            except errors.CompoundError as validation_error:
                for error in validation_error.errors:
                    flask.flash(error.message, 'error')


        return self


class BoundForm(Form):

    mode = None
    model = None
    instance = None

    class Meta:
        abstract = True

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


class AddForm(BoundForm):

    def __new__(cls, model_or_instance, mode='add', prefix=None, name=None, title=None, method=None, action=None):
        f = super(AddForm, cls).__new__(cls, model_or_instance, prefix=prefix, name=name, title=title, method=method, action=action)

        for field in f.model._meta.sorted_fields:

            if not field.name in f.model.form_blacklist and \
                not f.fields.has_key(field.name): # means this field was already defined in the class definition for this form

                kw = {}
                kw['name'] = field.name
                kw['default'] = field.default
                
                if field.null == False:
                    kw['required'] = True

                if isinstance(field, poobrains.storage.fields.ForeignKeyField):
                    #TODO: is this the place to do permission checking for the field?

                    kw['choices'] = []
                    for choice in field.rel_model.select():
                        if hasattr(choice, 'name') and choice.name:
                            choice_name = choice.name
                        else:
                            choice_name = "%s #%d" % (choice.__class__.__name__, choice.id)
                        kw['choices'].append((choice.handle_string, choice_name))


                form_field = field.form_class(**kw)
                setattr(f, field.name, form_field)

            f.controls['reset'] = Button('reset', label='Reset')
            f.controls['submit'] = Button('submit', name='submit', value='submit', label='Save')

        return f

    
    def __init__(self, model_or_instance, mode='add', prefix=None, name=None, title=None, method=None, action=None):
        
        if not name:
            #name = '%s-%s' % (self.model.__name__, mode) if mode == 'add' else '%s-%s-%s' % (self.model.__name__, self.instance._get_pk_value(), mode)
            name = '%s-%s' % (self.model.__name__, self.instance.handle_string)
    
        super(AddForm, self).__init__(model_or_instance, mode=mode, prefix=prefix, name=name, title=title, method=method, action=action)

        if not title:
    
            if hasattr(self.instance, 'title') and self.instance.title:
                self.title = "%s %s '%s'" % (self.mode, self.model.__name__, self.instance.title)
            elif self.instance.name:
                self.title = "%s %s '%s'" % (self.mode, self.model.__name__, self.instance.name)
            elif self.instance.id:
                self.title = "%s %s #%d" % (self.mode, self.model.__name__, self.instance.id)
            else:
                try:

                    if self.instance._get_pk_value():
                        self.title = "%s %s '%s'" % (self.mode, self.model.__name__, self.instance._get_pk_value())
                    else:
                        self.title = "%s %s" % (self.mode, self.model.__name__)

                except Exception as e:
                    self.title = "%s %s" % (self.mode, self.model.__name__)

        for name, field in self.fields.iteritems():
            if hasattr(self.instance, name):
                try:
                    field.value = getattr(self.instance, name)
                except Exception as e:
                    pass
 

    def handle(self):
        if not self.readonly:

            for field in self.model._meta.sorted_fields:
                if not field.name in self.model.form_blacklist:
                    #if self.fields[field.name].value is not None: # see https://github.com/coleifer/peewee/issues/107
                    if not self.fields[field.name].empty():
                        setattr(self.instance, field.name, self.fields[field.name].value)

            try:

                if self.mode == 'add':
                    saved = self.instance.save(force_insert=True) # To make sure Administerables with CompositeKey as primary get inserted properly
                else:
                    saved = self.instance.save()

                if saved:
                    flask.flash("Saved %s %s." % (self.model.__name__, self.instance.handle_string))
                    try:
                        return flask.redirect(self.instance.url('edit'))
                    except LookupError:
                        return self
                else:
                    flask.flash("Couldn't save %s." % self.model.__name__)

            except peewee.IntegrityError as e:
                flask.flash('Integrity error: %s' % e.message, 'error')

        else:
            flask.flash("Not handling readonly form '%s'." % self.name)

        return self


class EditForm(AddForm):
    
    def __new__(cls, model_or_instance, mode='edit', prefix=None, name=None, title=None, method=None, action=None):
        f = super(EditForm, cls).__new__(cls, model_or_instance, mode=mode, prefix=prefix, name=name, title=title, method=method, action=action)
        for pkfield in f.model._meta.get_primary_key_fields():
            if f.fields.has_key(pkfield.name):
                f.fields[pkfield.name].readonly = True # Make any primary key fields read-only

        return f

   

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

        return flask.redirect(self.model.url('teaser')) # TODO app.admin.get_listing_url?


class Fieldset(BaseForm):

    errors = None
    readonly = None
    rendered = None
    _default = werkzeug.MultiDict()

    class Meta:
        abstract = True
        clone_props = ['name', 'title']


    def __init__(self, *args, **kw):

        self.rendered = False
        self.readonly = False
        self.errors = []
        super(Fieldset, self).__init__(*args, **kw)
    

    def render(self, mode=None):

        self.rendered = True
        return super(Fieldset, self).render(mode)


    def __setattr__(self, name, value):

        if name == 'value':
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

    class Meta:
        clone_props = ['type', 'name', 'value', 'label']
    
    def __init__(self, type, name=None, value=None, label=None):

        super(Button, self).__init__()

        self.name = name
        self.type = type
        self.value = value
        self.label = label
