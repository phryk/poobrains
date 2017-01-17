# -*- coding: utf-8 -*-

# external imports
import math
import collections
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
#    def __new__(cls, name, bases, attrs):
#
#        cls = super(BaseModel, cls).__new__(cls, name, bases, attrs)
#        if hasattr(cls, '_meta'):
#            cls._meta._additional_keys = cls._meta._additional_keys - set(['abstract']) # This makes the "abstract" property non-inheritable.
#            #TODO: Seems hacky as fuck, might be a good idea to ask cleifer whether this is proper.
#
#        return cls


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
        #pkfields = self._meta.get_primary_key_fields()

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
    def class_view(cls, mode, handle):

        instance = cls.load(cls.string_handle(handle))
        return instance.view(mode, handle)


    @classmethod
    def list(cls, op, user, handles=None):

        query = cls.select()

        if handles:
            poobrains.app.debugger.set_trace()
            keyed_handles = collections.OrderedDict()
            for field_name in cls._meta.handle_fields:
                keyed_handles[field_name] = []

            for handle in handles:
               
                #handle = cls.string_handle(handle) # TODO: remove if we can be sure only raw handles are used, not their string representations
                for field_name in cls._meta.handle_fields:
                    idx = cls._meta.handle_fields.index(field_name) 
                    keyed_handles[field_name].append(handle[idx])

            #query = peewee.where(cls.id._in(processed_handles))
            for field_name in cls._meta.handle_fields:
                field = getattr(cls, field_name)
                query = query.where(field.in_(keyed_handles[field_name]))
                
        return query


class Named(Storable):

    name = fields.CharField(index=True, unique=True, null=False, constraints=[RegexpConstraint('name', '^[@a-z0-9_\-\.]+$')])

    def __init__(self, *args, **kwargs):

        super(Named, self).__init__(*args, **kwargs)


    def instance_url(self, mode='full'):
        return app.get_url(self.__class__, handle=self.name, mode=mode)


class Listing(rendering.Renderable):

    #TODO: Make a Listing class that works with non-Storable Renderables

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
    actions = None

    def __init__(self, cls, mode='teaser', title=None, offset=0, limit=None, actions=None):

        super(Listing, self).__init__()
        self.cls = cls
        self.mode = mode
        self.offset = offset
        self.actions = actions

        if title is not None:
            self.title = title
        else:
            self.title = cls.__name__

        if limit is None:
            self.limit = app.config['PAGINATION_COUNT']
        else:
            self.limit = limit

        #select = cls.select()
        op = cls._meta.modes[mode]
        select = cls.list(op, flask.g.user)
        self.count = select.count()

        self.pagecount = int(math.ceil(self.count/float(self.limit)))
        self.current_page = int(math.floor(self.offset / float(self.limit))) + 1

        #self.items = []
        #items = select.offset(self.offset).limit(self.limit)
        self.items = select.offset(self.offset).limit(self.limit)

        #iteration_done = False
        #iterator = items.__iter__()
        #while not iteration_done:
        #    try:
        #        item = next(iterator)
        #        self.items.append(item)

        #    except StopIteration:
        #        iteration_done = True

        # Build pagination if matching endpoint and enough rows exist
        endpoint = flask.request.endpoint
        if not endpoint.endswith('_offset'):
            endpoint = '%s_offset' % (endpoint,)

        try:

            self.pagination = rendering.Menu('pagination')
            for i in range(0, self.pagecount):

                page_num = i+1
                active = self.current_page == page_num

                self.pagination.append(
                    flask.url_for(endpoint, offset=i*self.limit),
                    page_num,
                    active
                )

            if len(self.pagination) < 2:
                self.pagination = False

        except werkzeug.routing.BuildError as e:
            app.logger.error('Pagination navigation could not be built. This might be fixable with more magic.')
            self.pagination = False


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
