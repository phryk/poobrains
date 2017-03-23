# -*- coding: utf-8 -*-

# external imports
import math
import collections
import re
import copy
import flask
import werkzeug.routing
import peewee

# parent imports
from poobrains import app
from poobrains import helpers
from poobrains import rendering
from poobrains import form
import poobrains
# internal imports
import fields

if isinstance(poobrains.app.db, peewee.SqliteDatabase):

    @poobrains.app.db.func('regexp')
    def nonretardedsqliteregexp(regexp, value):
        return re.search(regexp, value) is not None


def RegexpConstraint(field_name, regexp):

    return peewee.Clause(
            peewee.SQL('CHECK('),
            peewee.Expression(
                QuotedSQL(field_name),
                peewee.OP.REGEXP,
                QuotedSQL(regexp),
                flat=True
            ),
            peewee.SQL(')'),
    )


class QuotedSQL(peewee.Entity):

    def __getattr__(self, attr):

        return super(peewee.Node, self).__getattr__(attr) # Is this a good idea?



class BaseModel(helpers.MetaCompatibility, peewee.BaseModel):

    pass


class Model(peewee.Model, helpers.ChildAware):

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

            if isinstance(segment, poobrains.storage.Model):
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


class Storable(Model, rendering.Renderable):

    class Meta:
        abstract = True


    def __init__(self, *args, **kwargs):

        super(Storable, self).__init__(*args, **kwargs)
        self.url = self.instance_url # make .url callable for class and instances


    def instance_url(self, mode='full'):

        return app.get_url(self.__class__, handle=self.handle_string, mode=mode)


    @classmethod
    def class_view(cls, mode, handle, **kwargs):

        instance = cls.load(cls.string_handle(handle))
        return instance.view(mode, handle, **kwargs)


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

    name = fields.CharField(index=True, unique=True, null=False, constraints=[RegexpConstraint('name', '^[a-z0-9_\-]+$')])

    def __init__(self, *args, **kwargs):

        super(Named, self).__init__(*args, **kwargs)


    def instance_url(self, mode='full'):
        return app.get_url(self.__class__, handle=self.name, mode=mode)


class Listing(rendering.Renderable):

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

    def __init__(self, cls, mode='teaser', title=None, query=None, offset=0, limit=None, menu_actions=None):

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
        
        pagination = Pagination({cls: query}, offset, endpoint)

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
            self.limit = poobrains.app.config['PAGINATION_COUNT']

        self.menu = False
        self.counts = dict([(cls, q.count()) for cls, q in self.queries.iteritems()])
        self.results = []
        self.page_info = collections.OrderedDict()
        self.num_results = sum([x.count() for x in self.queries.itervalues()])
        self.num_pages = int(math.ceil(float(self.num_results) / self.limit))
        self.current_page = int(math.floor(self.offset / float(self.limit))) + 1

        position = 0

        range_lower = self.offset
        range_upper = self.offset + self.limit - 1

        for administerable, count in self.counts.iteritems():

            if count > 0:

                first_position = position
                last_position = first_position + count - 1

                on_current_page = first_position <= range_upper and last_position >= range_lower

                if on_current_page:
                
                    self.page_info[administerable] = {}

                    starts_before_page = first_position < range_lower
                    starts_within_page = first_position >= range_lower and first_position <= range_upper
                    ends_after_page = last_position > range_upper

                    if starts_before_page:
                        self.page_info[administerable]['offset'] = range_lower - first_position
                    else:
                        self.page_info[administerable]['offset'] = 0

                    if starts_within_page and ends_after_page:
                        self.page_info[administerable]['limit'] = self.limit - (first_position - range_lower)
                    else:
                        self.page_info[administerable]['limit'] = self.limit

                position += count


        for administerable, info in self.page_info.iteritems():

            query = self.queries[administerable]

            query = query.offset(info['offset'])
            query = query.limit(info['limit'])
            self.queries[administerable] = query # is this needed or is it just a reference?

            for result in query:
                self.results.append(result)


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
