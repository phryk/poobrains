# -*- coding: utf-8 -*-

# external imports
import math
import collections
import re
import copy
import click
import flask
import werkzeug.routing
import peewee

# parent imports
#import poobrains
from poobrains import app
import poobrains.helpers
import poobrains.rendering
import poobrains.form
# internal imports
from . import fields

if isinstance(app.db, peewee.SqliteDatabase):

    @app.db.func('regexp')
    def nonretardedsqliteregexp(regexp, value):
        return re.search(regexp, value) is not None


def RegexpConstraint(field_name, regexp):

    if 'sqlite' in app.db.__class__.__name__.lower():
        regexp_compat = QuotedSQL(regexp)
    else:
        regexp_compat = regexp

    return peewee.Clause(
            peewee.SQL('CHECK('),
            peewee.Expression(
                QuotedSQL(field_name),
                peewee.OP.REGEXP,
                regexp_compat,
                flat=True
            ),
            peewee.SQL(')'),
    )


class QuotedSQL(peewee.Entity):

    def __getattr__(self, attr):

        return super(peewee.Node, self).__getattr__(attr) # Is this a good idea?



class BaseModel(poobrains.helpers.MetaCompatibility, peewee.BaseModel):

    pass


class Model(peewee.Model, poobrains.helpers.ChildAware):

    __metaclass__ = BaseModel
    
    form_blacklist = ['id'] # What fields to ignore when generating an AutoForm for this class

    class Meta:
        database = app.db
        order_by = ['-id']


    @classmethod
    def load(cls, handle):

        q = cls.select()

        if type(handle) not in (tuple, list):
            handle = [handle]

        assert len(handle) == len(cls._meta.handle_fields)

        for field_name in cls._meta.handle_fields:
            field = getattr(cls, field_name)
            idx = cls._meta.handle_fields.index(field_name)
            q = q.where(field == handle[idx])

        return q.get()


    @property
    def handle_string(self):

        segments = []

        for field_name in self._meta.handle_fields:
            try:
                segment = getattr(self, field_name)
            except peewee.DoesNotExist: # Means we have a ForeignKey without assigned/valid value.
                segment = None

            if isinstance(segment, Model):
                segment = str(segment._get_pk_value())
            else:
                segment = str(segment)

            segments.append(segment)

        return ':'.join(segments)


    @classmethod
    def string_handle(cls, string):
        
        if string.find(':'):
            return tuple(string.split(':'))

        return string


    def __repr__(self):
        try:
            return "<%s[%s]>" % (self.__class__.__name__, self._get_pk_value())
        except Exception:
            return "<%s, unsaved/no primary key>" % self.__class__.__name__


class Storable(Model, poobrains.rendering.Renderable):

    class Meta:
        abstract = True
        modes = collections.OrderedDict([('full', 'read')])

    def __init__(self, *args, **kwargs):

        super(Storable, self).__init__(*args, **kwargs)
        self.url = self.instance_url # make .url callable for class and instances

    
    @property
    def title(self):
        if self.name:
            return self.name

        elif self.id:
            return "%s #%d" % (self.__class__.__name__, self.id)

        return self.__class__.__name__


    def instance_url(self, mode='full', quiet=False, **url_params):

        if quiet:
            try:
                return app.get_url(self.__class__, handle=self.handle_string, mode=mode, **url_params)
            except:
                return False

        return app.get_url(self.__class__, handle=self.handle_string, mode=mode, **url_params)


    @classmethod
    def class_view(cls, mode='teaser', handle=None, **kwargs):

        instance = cls.load(cls.string_handle(handle))
        return instance.view(handle=handle, mode=mode, **kwargs)


    @classmethod
    def list(cls, op, user, handles=None):

        query = cls.select()

        if handles:
            
            keyed_handles = collections.OrderedDict()
            for field_name in cls._meta.handle_fields:
                keyed_handles[field_name] = []

            for handle in handles:
               
                for field_name in cls._meta.handle_fields:
                    idx = cls._meta.handle_fields.index(field_name) 
                    keyed_handles[field_name].append(handle[idx])

            for field_name in cls._meta.handle_fields:
                field = getattr(cls, field_name)
                query = query.where(field.in_(keyed_handles[field_name]))
                
        return query


class Named(Storable):

    class Meta:
        handle_fields = ['name']

    name = fields.CharField(index=True, unique=True, null=False, constraints=[RegexpConstraint('name', '^[a-z0-9_\-]+$')])

    def __init__(self, *args, **kwargs):

        super(Named, self).__init__(*args, **kwargs)


    def instance_url(self, mode='full', quiet=False, **url_params):

        if quiet:
            try:
                return app.get_url(self.__class__, handle=self.name, mode=mode, **url_params)
            except:
                return False

        return app.get_url(self.__class__, handle=self.name, mode=mode, **url_params)


class Listing(poobrains.rendering.Renderable):

    #TODO: Make a Listing class that works with non-Storable Renderables?

    cls = None
    mode = None
    title = None
    offset = None
    limit = None
    items = None
    pagecount = None
    count = None
    pagination = None
    current_page = None
    menu_actions = None

    def __init__(self, cls, mode='teaser', title=None, query=None, offset=0, limit=None, menu_actions=None, **pagination_options):

        super(Listing, self).__init__()
        self.cls = cls
        self.mode = mode
        self.offset = offset
        self.menu_actions = menu_actions

        if title is not None:
            self.title = title
        else:
            self.title = cls.__name__

        if limit is None:
            self.limit = app.config['PAGINATION_COUNT']
        else:
            self.limit = limit

        if query is None:
            op = cls._meta.modes[mode]
            query = cls.list(op, flask.g.user)


        endpoint = flask.request.endpoint
        if not endpoint.endswith('_offset'):
            endpoint = '%s_offset' % (endpoint,)
        
        pagination = Pagination([query], offset, endpoint, **pagination_options)

        self.items = pagination.results
        self.pagination = pagination.menu


    def templates(self, mode=None):

        tpls = []

        for x in [self.__class__] + self.__class__.ancestors():

            name = x.__name__.lower()
                
            if mode:
                if issubclass(x, Listing):
                    tpls.append('%s-%s-%s.jinja' % (name, mode, self.cls.__name__))
                tpls.append('%s-%s.jinja' % (name, mode))

            tpls.append('%s.jinja' % name)

        return tpls


class Pagination(object):

    menu = None # the actual pagination menu
    options = None # optional parameters for flask.url_for
    limit = None
    offset = None
    queries = None
    counts = None
    results = None
    page_info = None
    num_results = None
    num_pages = None
    current_page = None


    def __init__(self, queries, offset, endpoint, limit=None, **options):
        
        self.queries = queries
        self.offset = offset
        self.endpoint = endpoint
        self.options = options

        if limit is not None:
            self.limit = limit
        else:
            self.limit = app.config['PAGINATION_COUNT']

        self.menu = False
        #self.counts = dict([(cls, q.count()) for cls, q in self.queries.iteritems()])
        #self.counts = dict([(q.model_class, q.count()) for q in self.queries])
        self.counts = collections.OrderedDict([(q, q.count()) for q in self.queries])
        self.results = []
        self.page_info = collections.OrderedDict()
        self.num_results = sum(self.counts.itervalues())
        self.num_pages = int(math.ceil(float(self.num_results) / self.limit))
        self.current_page = int(math.floor(self.offset / float(self.limit))) + 1

        position = 0

        range_lower = self.offset
        range_upper = self.offset + self.limit - 1

        for query, count in self.counts.iteritems():

            if count > 0:

                first_position = position
                last_position = first_position + count - 1

                on_current_page = first_position <= range_upper and last_position >= range_lower

                if on_current_page:
                
                    self.page_info[query] = {}

                    starts_before_page = first_position < range_lower
                    starts_within_page = first_position >= range_lower and first_position <= range_upper
                    ends_after_page = last_position > range_upper

                    if starts_before_page:
                        query = query.offset(range_lower - first_position)
                    else:
                        query = query.offset(0)

                    if starts_within_page and ends_after_page:
                        query = query.limit(self.limit - (first_position - range_lower))
                    else:
                        query = query.limit(self.limit)

                    for result in query:
                        self.results.append(result)

                position += count

        if self.num_pages > 1:

            self.menu = poobrains.rendering.Menu('pagination')

            for i in range(0, self.num_pages):

                page_num = i + 1
                active = page_num == self.current_page
                kw = copy.copy(self.options)
                kw['offset'] = i * self.limit

                self.menu.append(
                    flask.url_for(self.endpoint, **kw),
                    page_num,
                    active
                )


class BoundForm(poobrains.form.Form):

    mode = None
    model = None
    instance = None

    class Meta:
        abstract = True

    def __new__(cls, model_or_instance, mode=None, prefix=None, name=None, title=None, method=None, action=None):

        f = super(BoundForm, cls).__new__(cls, prefix=prefix, name=name, title=title, method=method, action=action)

        if isinstance(model_or_instance, type(Model)): # hacky
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

                if field.form_class is not None:
                    form_field = field.form_class(**kw)
                    setattr(f, field.name, form_field)

            f.controls['reset'] = poobrains.form.Button('reset', label='Reset')
            f.controls['submit'] = poobrains.form.Button('submit', name='submit', value='submit', label='Save')

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
 

    def process(self, exceptions=False):

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

                            fieldset.process(self.instance)

                        except Exception as e:

                            if exceptions:
                                raise

                            flask.flash(u"Failed to process fieldset '%s.%s'." % (fieldset.prefix, fieldset.name), 'error')
                            app.logger.error(u"Failed to process fieldset %s.%s - %s: %s" % (fieldset.prefix, fieldset.name, type(e).__name__, e.message.decode('utf-8')))

                    try:
                        return flask.redirect(self.instance.url('edit'))
                    except LookupError:
                        return self
                else:

                    flask.flash(u"Couldn't save %s." % self.model.__name__)

            except peewee.IntegrityError as e:

                if exceptions:
                    raise

                flask.flash(u'Integrity error: %s' % e.message.decode('utf-8'), 'error')
                app.logger.error(u"Integrity error: %s" % e.message.decode('utf-8'))

            except Exception as e:

                if exceptions:
                    raise

                flask.flash(u"Couldn't save %s. %s: %s" % self.model.__name__, type(e).__name__, e.message.decode('utf-8'))

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
        f.warning = poobrains.form.fields.Message('deletion_irrevocable', value='Deletion is not revocable. Proceed?')
        f.submit = poobrains.form.Button('submit', name='submit', value='delete', label=u'☠')

        return f


    def __init__(self, model_or_instance, mode='delete', prefix=None, name=None, title=None, method=None, action=None):
        super(DeleteForm, self).__init__(model_or_instance, mode=mode, prefix=prefix, name=self.name, title=title, method=method, action=action)
        if not title:
            if hasattr(self.instance, 'title') and self.instance.title:
                self.title = "Delete %s %s" % (self.model.__name__, self.instance.title)
            else:
                self.title = "Delete %s %s" % (self.model.__name__, unicode(self.instance._get_pk_value()))

    
    def process(self):

        if hasattr(self.instance, 'title') and self.instance.title:
            message = "Deleted %s '%s'." % (self.model.__name__, self.instance.title)
        else:
            message = "Deleted %s '%s'." % (self.model.__name__, unicode(self.instance._get_pk_value()))
        self.instance.delete_instance()
        flask.flash(message)

        return flask.redirect(self.model.url('teaser')) # TODO app.admin.get_listing_url?


class AddFieldset(AddForm, poobrains.form.Fieldset):

    rendered = None


    def __new__(cls, *args, **kwargs):

        f = super(AddFieldset, cls).__new__(cls, *args, **kwargs)
        f.controls.clear()

        return f
    

    def render(self, mode=None):

        self.rendered = True
        return super(AddFieldset, self).render(mode)


class EditFieldset(EditForm, poobrains.form.Fieldset):

    rendered = None
 
    def render(self, mode=None):

        self.rendered = True
        return super(EditFieldset, self).render(mode)


class StorableParamType(poobrains.form.types.ParamType):

    baseclass = None

    def __init__(self, baseclass=Storable):

        super(StorableParamType, self).__init__()
        self.baseclass = baseclass

    def convert(self, value, param, ctx):

        if isinstance(value, self.baseclass):
            return value # apparently we need this function to be idempotent? Didn't even knew that was a real word.

        storables = {k.lower(): v for k, v in self.baseclass.class_children_keyed().iteritems()}

        if storables.has_key(value.lower()):
            return storables[value.lower()] # holy shit it's lined up! D:

        self.fail(u'Not a valid storable: %s. Try one of %s' % (value, storables.keys()))

poobrains.form.types.StorableParamType = StorableParamType
poobrains.form.types.STORABLE = StorableParamType()
