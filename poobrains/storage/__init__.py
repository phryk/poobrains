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
        return cls.get(cls._meta.primary_key == handle)


    @property
    def handle_string(self):

        segments = []
        pkfields = self._meta.get_primary_key_fields()

        for pkfield in pkfields:
            try:
                segment = getattr(self, pkfield.name)
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
        self.templates = self.instance_templates
        self.url = self.instance_url # make .url callable for class and instances


    def instance_url(self, mode='full'):

        return app.get_url(self.__class__, handle=self.handle_string, mode=mode)


    @classmethod
    def templates(cls, mode='full'):
        return super(Storable, cls).templates(mode) 


    def instance_templates(self, mode='edit'):
        return self.__class__.templates(mode)
    
    
    @classmethod
    def class_view(cls, mode, handle):

        instance = cls.load(cls.string_handle(handle))
        return instance.view(mode, handle)


    @classmethod
    def list(cls, mode, user):
        return cls.select()


class Named(Storable):

    name = fields.CharField(index=True, unique=True, null=False, constraints=[RegexpConstraint('name', '^[@a-z0-9_\-]+$')])

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
