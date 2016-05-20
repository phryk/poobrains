# -*- coding: utf-8 -*-

# external imports
import math
import flask
import werkzeug.routing
import peewee

# parent imports
from poobrains import app
from poobrains import helpers
from poobrains import rendering
from poobrains import form

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

    class Meta:
        database = app.db
        order_by = ['-id']


    @classmethod
    def load(cls, id):
        return cls.get(cls.id == id)


    def __repr__(self):
        return "<%s[%s]>" % (self.__class__.__name__, self.id) if self.id else "<%s, unsaved.>" % self.__class__.__name__


class Storable(Model, rendering.Renderable):

    field_blacklist = ['id'] # What fields to ignore when generating an AutoForm for this class


    class Meta:
        abstract = True


    def __init__(self, *args, **kwargs):

        super(Storable, self).__init__(*args, **kwargs)
        self.url = self.instance_url # make .url callable for class and instances
        self.form = self.instance_form # make .form callable for class and instance


    @classmethod
    def url(cls, mode=None):
        return app.get_url(cls, mode=mode)


    def instance_url(self, mode=None):
        return app.get_url(self.__class__, id_or_name=self.name, mode=mode)


    @classmethod
    def form(cls):

        return cls().form('add')


    def instance_form(self, mode='edit'):

        if mode == 'add':
            title = 'Add new %s' % (self.__class__.__name__,)
        else:
            title = self.title if hasattr(self, 'title') else self.name

        f = form.AutoForm(self, mode=mode, title=title, action=self.url(mode))

        return f
   

    def render(self, mode='full'):

        if mode in ('add', 'edit', 'delete'):

            if mode == 'add':
                form = self.__class__.form()

            else:
                form = self.form(mode=mode)

            return form.render()

        return super(Storable, self).render(mode=mode)



class Listing(rendering.Renderable):

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

        select = cls.select()
        self.count = select.count()

        self.pagecount = int(math.ceil(self.count/float(self.limit)))
        self.current_page = int(math.floor(self.offset / float(self.limit))) + 1

        self.items = []
        items = select.offset(self.offset).limit(self.limit)

        iteration_done = False
        iterator = items.__iter__()
        while not iteration_done:
            try:
                item = next(iterator)
                self.items.append(item)

            except StopIteration:
                iteration_done = True

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
