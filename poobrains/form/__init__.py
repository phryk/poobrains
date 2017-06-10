# -*- coding: utf-8 -+-

# external imports
import time
import copy
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

    def __new__(cls, name, bases, attrs):
        return super(FormMeta, cls).__new__(cls, name, bases, attrs)

    def __setattr__(cls, name, value):
        return super(FormMeta, cls).__setattr__(name, value)


class BaseForm(poobrains.rendering.Renderable):

    __metaclass__ = FormMeta

    class Meta:
        abstract = True

    _external_fields = None

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
            if isinstance(attr, fields.Field) or isinstance(attr, Fieldset) or isinstance(attr, Button): # FIXME: This should be doable with just one check
                clone_attributes.append((attr_name, attr))

        for (attr_name, attr) in sorted(clone_attributes, key=lambda x: getattr(x[1], '_created')):

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
    
    
    def __init__(self, prefix=None, name=None, title=None):

        self._external_fields = []
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
            if isinstance(field, (fields.RenderableField, Fieldset)) and field.name not in self._external_fields:
                yield field

    
    def _add_external_field(self, field):

        """
        Add a field which is to be rendered outside of this form, but handled by it.
        Fields like this can be created by passing a Form object to the Field constructor.
        """

        if isinstance(field, fields.MultiCheckbox) and self.fields.has_key(field.name) and type(field) == type(self.fields[field.name]): # checkboxes/radio inputs can pop up multiple times, but belong to the same name
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
        if self.prefix:
            return "%s-%s" % (self.prefix, self.name)
        return self.name

    def empty(self): # TODO: find out why I didn't make this @property
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

            actionable_fields = [f for f in self]
            actionable_fields += [self.fields[name] for name in self._external_fields]

            for field in actionable_fields:

                if not field.readonly:
                    
                    source = files if isinstance(field, fields.File) else values
                    if source.has_key(field.name):
                        if field.multi:
                            field_values = source.getlist(field.name)
                        else:
                            field_values = source[field.name]

                    else:
                            field_values = field._default
                    
                    try:
                        if isinstance(field, Fieldset):
                            sub_files = files[field.name] if files.has_key(field.name) else werkzeug.datastructures.MultiDict()
                            field.bind(field_values, sub_files) # FIXME: This is probably wrong. files[field.name] if exists or sth like that
                        else:
                            field.bind(field_values)

                    except errors.ValidationError as e:
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


    def handle(self):

        raise NotImplementedError("%s.handle not implemented." % self.__class__.__name__)


class Form(BaseForm):

    method = None
    action = None

    class Meta:
        abstract = True

    def __init__(self, prefix=None, name=None, title=None, method=None, action=None, **kwargs):

        super(Form, self).__init__(prefix=prefix, name=name, title=title)
        self.method = method if method else 'POST'
        self.action = action if action else ''


    @classmethod
    def class_view(cls, mode='full', **kwargs):

        instance = cls(**kwargs)
        return instance.view(mode)


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
            #TODO: filter self.readonly in here instead of .bind and .handle?
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

        if hasattr(f.instance, 'menu_actions'):
            f.menu_actions = f.instance.menu_actions

        if hasattr(f.instance, 'menu_related'):
            f.menu_related = f.instance.menu_related

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
                
                if field.null == False and field.default is None:
                    kw['required'] = True
                else:
                    kw['required'] = False

                if isinstance(field, poobrains.storage.fields.ForeignKeyField):
                    #TODO: is this the place to do permission checking for the field?

                    kw['choices'] = []
                    for choice in field.rel_model.select():
                        if hasattr(choice, 'name') and choice.name:
                            choice_name = choice.name
                        else:
                            choice_name = "%s #%d" % (choice.__class__.__name__, choice.id)
                        kw['choices'].append((choice.handle_string, choice_name))


                if field.form_class is not None:
                    form_field = field.form_class(**kw)
                    setattr(f, field.name, form_field)

            f.controls['reset'] = Button('reset', label='Reset')
            f.controls['submit'] = Button('submit', name='submit', value='submit', label='Save')

        return f

    
    def __init__(self, model_or_instance, mode='add', prefix=None, name=None, title=None, method=None, action=None):
        
        if not name:
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
 

    def handle(self, exceptions=False):

        if not self.readonly:
            
            for field in self.model._meta.sorted_fields:
                if not field.name in self.model.form_blacklist:
                    #if self.fields[field.name].value is not None: # see https://github.com/coleifer/peewee/issues/107
                    if not self.fields[field.name].empty():
                        setattr(self.instance, field.name, self.fields[field.name].value)
                    elif field.default is not None:
                        setattr(self.instance, field.name, field.default() if callable(field.default) else field.default)
                    elif field.null:
                        setattr(self.instance, field.name, None)


            try:

                if self.mode == 'add':
                    saved = self.instance.save(force_insert=True) # To make sure Administerables with CompositeKey as primary get inserted properly
                else:
                    saved = self.instance.save()

                if saved:
                    flask.flash(u"Saved %s %s." % (self.model.__name__, self.instance.handle_string))

                    for fieldset in self.fieldsets:
                        try:
                            fieldset.handle(self.instance)
                        except Exception as e:
                            if exceptions:
                                raise
                            flask.flash(u"Failed to handle fieldset '%s.%s'." % (fieldset.prefix, fieldset.name))
                            poobrains.app.logger.error("Failed to handle fieldset %s.%s - %s: %s" % (fieldset.prefix, fieldset.name, type(e).__name__, e.message))

                    try:
                        return flask.redirect(self.instance.url('edit'))
                    except LookupError:
                        return self
                else:
                    flask.flash(u"Couldn't save %s." % self.model.__name__)

            except peewee.IntegrityError as e:

                if exceptions:
                    raise
                flask.flash(u'Integrity error: %s' % e.message, 'error')

        else:
            flask.flash(u"Not handling readonly form '%s'." % self.name)

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


    def handle(self):

        raise NotImplementedError("%s.handle not implemented." % self.__class__.__name__)


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
