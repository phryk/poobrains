# -*- coding: utf-8 -*-

import math
from collections import OrderedDict
from flask import abort, render_template, url_for, current_app, request
import werkzeug.routing
import peewee
from .rendering import ChildAware, Renderable, Menu
from .helpers import CustomOrderedDict

import logging
logger = logging.getLogger('peewee')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

proxy = peewee.Proxy()


class OperationalError(peewee.OperationalError):
    code = 500


class IntegrityError(peewee.IntegrityError):
    code = 400


class DoesNotExist(peewee.DoesNotExist):
    code = 404


class QuotedSQL(peewee.Entity):

    def __getattr__(self, attr):

        return super(peewee.Node, self).__getattr__(attr) # Is this a good idea?


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


class Model(peewee.Model, ChildAware):
    
    class Meta:
        database = proxy


    class DoesNotExist(DoesNotExist):
        pass


class Storable(Model, Renderable):

    field_blacklist = ['id']
    name = peewee.CharField(index=True, unique=True, constraints=[RegexpConstraint('name', '^[a-zA-Z0-9_\-]*$')])
    title = peewee.CharField()
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

#        except cls.DoesNotExist:
#            abort(404, "It is pitch black. You are likely to be eaten by a grue.")
#
#        except peewee.OperationalError:
#            if current_app.debug:
#                raise
#
#            abort(500, "Somebody set up us the bomb.")

        instance.actions = Menu('%s-%d.actions' % (instance.__class__.__name__, instance.id))
        try:
            instance.actions.append(instance.url('full'), 'View')
            instance.actions.append(instance.url('edit'), 'Edit')
            instance.actions.append(instance.url('delete'), 'Delete')

        except Exception as e:
            current_app.logger.error('Action menu generation failure.')
            current_app.logger.error(e)

        return instance


    @classmethod
    def url(cls, mode=None):
        return current_app.get_url(cls, mode=mode)


    def instance_url(self, mode=None):
        return current_app.get_url(self.__class__, id_or_name=self.name, mode=mode)


    @classmethod
    def form(cls):

        return cls().form('add')


    def instance_form(self, mode='edit'):

        if mode == 'add':
            title = 'Add new %s' % (self.__class__.__name__,)
        else:
            title = self.title

        form = Form(
            '%s-%s' % (self.__class__.__name__.lower(), mode),
            title=title,
            action=self.url(mode),
            tpls=self.form_template_candidates()
        )

        form.actions = self.actions

        if mode == 'delete':

            form.add_field('warning', 'message', value='Deletion is not revocable. Proceed?')
            form.add_button('submit', name='submit', value='delete', label='KILL')

        else:
            fields = self.__class__._meta.get_fields()

            for field in fields:
                form.add_field(field.name, field.__class__.__name__.lower(), getattr(self, field.name))

            form.add_button('reset', name='reset', label='Reset')
            form.add_button('submit', name='submit', value='save', label='Save')

        return form
        
    
    def form_template_candidates(self):

        tpls = []
        clsname = self.__class__.__name__.lower()
        tpls.append('%s-form.jinja' % (clsname,))

        for ancestor in self.__class__.ancestors(Storable):
            clsname = ancestor.__name__.lower()
            tpls.append('%s-form.jinja' % (clsname,))

        return tpls


    def render(self, mode='full'):

        if mode in ('add', 'edit', 'delete'):

            if mode == 'add':
                form = self.__class__.form()

            else:
                form = self.form(mode=mode)

            return form.render()

        return super(Storable, self).render(mode=mode)



class Listing(Renderable):

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
            self.limit = current_app.config['PAGINATION_COUNT']
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
        endpoint = request.endpoint
        if not endpoint.endswith('_offset'):
            endpoint = '%s_offset' % (endpoint,)

        try:

            self.pagination = Menu('pagination')
            for i in range(0, self.pagecount):

                page_num = i+1
                active = self.current_page == page_num

                self.pagination.append(
                    url_for(endpoint, offset=i*self.limit),
                    page_num,
                    active
                )

            if len(self.pagination) < 2:
                self.pagination = False

        except werkzeug.routing.BuildError as e:
            current_app.logger.error('Pagination navigation could not be built. This might be fixable with more magic.')
            self.pagination = False



class Form(Renderable):

    name = None
    title = None
    method = None
    fields = None
    controls = None
    rendered = None
    field_associations = None

    def __init__(self, name, title='', method='POST', action=None, tpls=None):
       
        self.name = name
        self.title = title
        self.method = method
        self.action = action
        self.fields = OrderedDict()
        self.controls = CustomOrderedDict()

        self.tpls = []
        if tpls:
            self.tpls += tpls
        
        self.tpls.append('form.jinja')

        self.render_reset()


    def template_candidates(self, mode):
        return self.tpls


    def add_field(self, name, field_type, value=None):
        self.fields[name] = (field_type, value)


    def add_button(self, type, name=None, value=None, label=None):

        self.controls[name] = Button(type, name=name, value=value, label=label)


    def render_reset(self):
        self.rendered = []


    def render_field(self, name):
        
        field_type, value = self.fields[name]

        tpls = ["fields/%s.jinja" % (field_type,)]
        tpls.append("fields/field.jinja")

        self.rendered.append(name)
        return render_template(tpls, field_type=field_type, name=name, value=value)


    def render_fields(self):
        
        rendered_fields = u''

        for name in self.fields.keys():

            if name not in self.rendered:
                rendered_fields += self.render_field(name)

        return rendered_fields



class Button(Renderable):

    name = None
    type = None
    value = None
    label = None

    
    def __init__(self, type, name=None, value=None, label=None):

        super(Button, self).__init__()

        self.name = name
        self.type = type
        self.value = value
        self.label = label
