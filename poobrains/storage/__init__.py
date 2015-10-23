# -*- coding: utf-8 -*-

# external imports
import math
import flask
import werkzeug.routing
import peewee

# parent imports
from poobrains import helpers
from poobrains import rendering
from poobrains import form

# internal imports
import fields
import cli


proxy = peewee.Proxy()

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



class Model(peewee.Model, helpers.ChildAware):
    
    class Meta:
        database = proxy



class Storable(Model, rendering.Renderable):

    field_blacklist = ['id']
    name = fields.CharField(index=True, unique=True, constraints=[RegexpConstraint('name', '^[a-zA-Z0-9_\-]*$')])
    title = fields.CharField()
    actions = None


    class Meta:
        order_by = ['-id']


    def __init__(self, *args, **kwargs):

        super(Storable, self).__init__(*args, **kwargs)
        self.url = self.instance_url # make .url callable for class and instances
        self.form = self.instance_form # make .form callable for class and instance



    @classmethod
    def load(cls, id_or_name):

#        try:
        if type(id_or_name) is int or (isinstance(id_or_name, basestring) and id_or_name.isdigit()):
            instance = cls.get(cls.id == id_or_name)

        else:
            instance = cls.get(cls.name == id_or_name)

        instance.actions = rendering.Menu('%s-%d.actions' % (instance.__class__.__name__, instance.id))
        try:
            instance.actions.append(instance.url('full'), 'View')
            instance.actions.append(instance.url('edit'), 'Edit')
            instance.actions.append(instance.url('delete'), 'Delete')

        except Exception as e:
            flask.current_app.logger.error('Action menu generation failure.')
            flask.current_app.logger.error(e)

        return instance


    @classmethod
    def url(cls, mode=None):
        return flask.current_app.get_url(cls, mode=mode)


    def instance_url(self, mode=None):
        return flask.current_app.get_url(self.__class__, id_or_name=self.name, mode=mode)


    @classmethod
    def form(cls):

        return cls().form('add')


    def instance_form(self, mode='edit'):

        if mode == 'add':
            title = 'Add new %s' % (self.__class__.__name__,)
        else:
            title = self.title

        f = form.Form(
            '%s-%s' % (self.__class__.__name__.lower(), mode),
            title=title,
            action=self.url(mode)
        )

        f.actions = self.actions

        if mode == 'delete':

            f.warning = form.fields.Warning('deletion_irrevocable', value='Deletion is not revocable. Proceed?')
            f.submit = form.Button('submit', name='submit', value='delete', label='KILL')

        else:
            own_fields = self.__class__._meta.get_fields()

            for field in own_fields:
                
                if isinstance(field, fields.Field):
                    flask.current_app.logger.debug(field)
                    form_field = field.form_class(field.name, value=getattr(self, field.name), validators=field.form_extra_validators)
                    setattr(f, field.name, form_field) 

            f.reset = form.Button('reset', label='Reset')
            f.submit = form.Button('submit', name='submit', value='save', label='Save')

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
            self.limit = flask.current_app.config['PAGINATION_COUNT']
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
            flask.current_app.logger.error('Pagination navigation could not be built. This might be fixable with more magic.')
            self.pagination = False
