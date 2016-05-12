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


@app.admin.box('menu_main')
def admin_menu():

    menu = rendering.Menu('main')
    menu.title = 'Administration'

    for storable, listings in app.admin.listings.iteritems():

        for mode, endpoints in listings.iteritems():

            for endpoint in endpoints: # iterates through endpoints.keys()
                menu.append(flask.url_for('admin.%s' % endpoint), storable.__name__)

    return menu


@app.admin.route('/')
@rendering.render()
def admin_index():
    return admin_menu()

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


class Permission(helpers.ChildAware):
   
    @classmethod
    def check(cls, user):
        return user.access(self)


class QuotedSQL(peewee.Entity):

    def __getattr__(self, attr):

        return super(peewee.Node, self).__getattr__(attr) # Is this a good idea?



class BaseModel(peewee.BaseModel):

    def __new__(cls, *args, **kwargs):

        cls.Create = type('%sCreate' % cls.__name__, (Permission,), {})
        cls.Read   = type('%sRead' % cls.__name__, (Permission,), {})
        cls.Update = type('%sUpdate' % cls.__name__, (Permission,), {})
        cls.Delete = type('%sDelete' % cls.__name__, (Permission,), {})

        return super(BaseModel, cls).__new__(cls, *args, **kwargs)


class Model(peewee.Model, helpers.ChildAware):

    __metaclass__ = BaseModel

    class Meta:
        database = app.db



class Storable(Model, rendering.Renderable):

    field_blacklist = ['id']
    name = fields.CharField(index=True, unique=True, constraints=[RegexpConstraint('name', '^[a-zA-Z0-9_\-]+$')])
    actions = None


    class Meta:
        order_by = ['-id']


    def __init__(self, *args, **kwargs):

        super(Storable, self).__init__(*args, **kwargs)
        self.url = self.instance_url # make .url callable for class and instances
        self.form = self.instance_form # make .form callable for class and instance

    @property
    def actions(self):

        if not self.id:
            return None

        actions = rendering.Menu('%s-%d.actions' % (self.__class__.__name__, self.id))
        try:
            actions.append(self.url('full'), 'View')
            actions.append(self.url('edit'), 'Edit')
            actions.append(self.url('delete'), 'Delete')

        except Exception as e:
            app.logger.error('Action menu generation failure.')
            app.logger.error(self)

        return actions

    @classmethod
    def load(cls, id_or_name):

        if type(id_or_name) is int or (isinstance(id_or_name, basestring) and id_or_name.isdigit()):
            instance = cls.get(cls.id == id_or_name)

        else:
            instance = cls.get(cls.name == id_or_name)


        return instance


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


    def __repr__(self):

        return "<%s[%s] %s>" % (self.__class__.__name__, self.id, self.name) if self.id else "<%s, unsaved.>" % self.__class__.__name__



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
