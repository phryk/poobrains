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

# import peewee error classes so projects can match these errors without importing peewee
from peewee import fn, CompositeKey, IntegrityError, DoesNotExist, DataError, DatabaseError, OperationalError, ProgrammingError

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

    operation = app.db._operations['REGEXP'] # peewee.OP.REGEXP used to always hold the correct value, what happen?

    if 'sqlite' in app.db.__class__.__name__.lower():
        regexp_compat = '"%s"' % regexp
    else:
        regexp_compat = "'%s'" % regexp

    return peewee.Check('"%s" %s %s' % (field_name, operation, regexp_compat))


class OrderableMetadata(peewee.Metadata):

    """
    This class ports over peewee _meta.order_by functionality, which was dropped in 3.0
    """

    order_by = None

    def prepared(self):

        if self.order_by:

            norm_order_by = []

            for item in self.order_by:

                if isinstance(item, peewee.Ordering):

                    # Orderings .node references a field specific to an upstream model.
                    # Therefore, we can't just adopt them.
                    if item.direction == 'DESC':
                        item = '-' + item.node.name
                    else:
                        item = item.node.name

                desc = False
                if item.startswith('-'):
                    desc = True
                    item = item[1:]

                field = self.fields[item]

                if desc:
                    norm_order_by.append(field.desc())
                else:
                    norm_order_by.append(field.asc())

        self.order_by = norm_order_by


class ModelBase(poobrains.helpers.MetaCompatibility, peewee.ModelBase):

    def __new__(cls, name, bases, attrs):

        cls = super(ModelBase, cls).__new__(cls, name, bases, attrs)
        cls._meta.prepared()

        return cls


class Model(peewee.Model, poobrains.helpers.ChildAware, metaclass=ModelBase):

    __metaclass__ = ModelBase

    class Meta:

        database = app.db
        model_metadata_class = OrderableMetadata # port of peewees dropped _meta.order_by feature
        order_by = ['-id']


    @classmethod
    def load(cls, handle):

        q = cls.select()

        if isinstance(handle, str):
            handle = cls.string_handle(handle)

        elif type(handle) not in (tuple, list):
            handle = [handle]

        assert len(handle) == len(cls._meta.handle_fields), "Handle length mismatch for %s, expected %d but got %d!" % (cls.__name__, len(cls._meta.handle_fields), len(handle))

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
                segment = str(segment._pk)
            else:
                segment = str(segment)

            #segment = segment.replace('.', ',') # since dots are used in FormDataParser to split data into a hierarchy, dots in field names will fuck shit up

            segments.append(segment)

        return ':'.join(segments)


    @classmethod
    def string_handle(cls, string):
        
        if string.find(':'):
            return tuple(string.split(':'))

        return string


    def validate(self):
        pass


    @classmethod
    def ordered(cls, *fields):

        query = cls.select(*fields)

        if cls._meta.order_by:
            query = query.order_by(*cls._meta.order_by)

        return query


    def save(self, *args, **kwargs):

        self.validate()
        return super(Model, self).save(*args, **kwargs)


    def __repr__(self):
        try:
            return "<%s[%s]>" % (self.__class__.__name__, self._pk)
        except Exception:
            return "<%s, unsaved/no primary key>" % self.__class__.__name__


class Storable(Model, poobrains.rendering.Renderable):

    """
    A `Renderable` `Model` associated to a single table in the database.
    """

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

        elif self._pk:
            return "%s %s" % (self.__class__.__name__, str(self._pk))

        return "New %s" % self.__class__.__name__


    def instance_url(self, mode='full', quiet=False, **url_params):

        if quiet:
            try:
                return app.get_url(self.__class__, handle=self.handle_string, mode=mode, **url_params)
            except:
                return False

        return app.get_url(self.__class__, handle=self.handle_string, mode=mode, **url_params)


    @classmethod
    def class_view(cls, mode='teaser', handle=None, **kwargs):

        instance = cls.load(handle)
        return instance.view(handle=handle, mode=mode, **kwargs)


    @classmethod
    def list(cls, op, user, handles=None, ordered=True, fields=[]):

        if ordered: # whether to use the default ordering for this model. mostly here because doing this *always* would break using this in UNIONs
            query = cls.ordered(*fields)
        else:
            query = cls.select(*fields)

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

    @property
    def ref_id(self):

        return "%s-%s" % (self.__class__.__name__.lower(), self.name)


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

    def __init__(self, cls, mode='teaser', title=None, query=None, offset=0, limit=None, menu_actions=None, menu_related=None, pagination_options=None, **kwargs):

        super(Listing, self).__init__(**kwargs)
        self.cls = cls
        self.mode = mode
        self.offset = offset
        self.menu_actions = menu_actions
        self.menu_related = menu_related

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

        if pagination_options is None:
            pagination_options = {}

        endpoint = flask.request.endpoint
        if not endpoint.endswith('_offset'):
            endpoint = '%s_offset' % (endpoint,)
        
        self.pagination = Pagination([query], offset, endpoint, **pagination_options)
        self.items = self.pagination.results


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
        self.counts = [(q, q.count()) for q in self.queries]
        self.results = []
        self.page_info = collections.OrderedDict()
        self.num_results = sum([x[1] for x in self.counts])
        self.num_pages = int(math.ceil(float(self.num_results) / self.limit))
        self.current_page = int(math.floor(self.offset / float(self.limit))) + 1

        position = 0

        range_lower = self.offset
        range_upper = self.offset + self.limit - 1

        for query, count in self.counts:

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


class StorableParamType(poobrains.form.types.ParamType):

    baseclass = None

    def __init__(self, baseclass=Storable):

        super(StorableParamType, self).__init__()
        self.baseclass = baseclass

    def convert(self, value, param, ctx):

        if value == '':
            return None

        if isinstance(value, self.baseclass):
            return value # apparently we need this function to be idempotent? Didn't even knew that was a real word.

        storables = self.baseclass.class_children_keyed(lower=True)

        if value.lower() in storables:
            return storables[value.lower()] # holy shit it's lined up! D:

        self.fail(u'Not a valid storable: %s. Try one of %s' % (value, storables.keys()))

poobrains.form.types.StorableParamType = StorableParamType
poobrains.form.types.STORABLE = StorableParamType()
