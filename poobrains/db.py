# -*- coding: utf-8 -*-

from math import ceil, floor
from re import match
from collections import OrderedDict
from flask import abort, render_template, url_for, current_app, request
from werkzeug.routing import BuildError
import peewee
from .rendering import ChildAware, Renderable, Menu

db_proxy = peewee.Proxy()


class ValidationError(ValueError):

    model = None
    field = None
    value = None

    def __init__(self, model, field, value):

        super(ValidationError, self).__init__()

        self.model = model
        self.field = field
        self.value = value

        self.message = "Tried assigning invalid value to %s.%s: %s" % (self.model.__name__, self.field.name, str(value))


    def __str__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.message)


class BaseModel(peewee.Model, ChildAware):
    
    class Meta:
        database = db_proxy



class Storable(BaseModel, Renderable):
    
    name = peewee.CharField(index=True, unique=True)
    title = peewee.CharField()


    class Meta:
        order_by = ['-id']


    def __init__(self, *args, **kwargs):

        super(Storable, self).__init__(*args, **kwargs)
        self.url = self.instance_url # make .url callable for class and instances
        self.form = self.instance_form # make .form callable for class and instance


    def __setattr__(self, name, value):

        if name == 'name' and not match('^[a-zA-ZäÄöÖüÜ_\-]*$', value):
            raise ValidationError(self.__class__, getattr(self.__class__, name), value)

        super(Storable, self).__setattr__(name, value)


    @classmethod
    def load(cls, id_or_name):

        try:
            if type(id_or_name) is int or (isinstance(id_or_name, basestring) and id_or_name.isdigit()):
                instance = cls.get(cls.id == id_or_name)

            else:
                instance = cls.get(cls.name == id_or_name)

        except cls.DoesNotExist:
            abort(404, "It is pitch black. You are likely to be eaten by a grue.")

        except peewee.OperationalError:
            if current_app.debug:
                raise

            abort(500, "Somebody set up us the bomb.")

        except ValidationError as e:

            current_app.logger.error("Database integrity impaired. Invalid data in %s.%s: %s" % (cls.__name__, e.field.name, e.value))

            if current_app.debug:
                raise

            abort(500, "VERY ERROR. SUCH DISGRACE. MANY SORRY.")

        return instance


    @classmethod
    def url(cls):
        return current_app.get_url(cls)


    def instance_url(self, mode=None):
        return current_app.get_url(self.__class__, id_or_name=self.name, mode=mode)


    @classmethod
    def form(cls):

        form = Form(self.__class__.__name__.lower()+'-add', action=cls.url('add'))

        fields = cls._meta.get_fields()

        for field in fields:
            form.add_field(field.name, field.__class__.__name__.lower())

        return form


    def instance_form(self):

        form = Form(self.__class__.__name__.lower()+'-edit', action=self.url('edit'))

        fields = self.__class__._meta.get_fields()

        for field in fields:
            form.add_field(field.name, field.__class__.__name__.lower(), getattr(self, field.name))

        return form


    def render(self, mode='full'):

        #TODO: get form if mode is 'add' or 'edit'
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

    def __init__(self, cls, mode='teaser', title=None, offset=0, limit=None):

        super(Listing, self).__init__()

        self.cls = cls
        self.mode = mode
        self.offset = offset

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

        self.pagecount = int(ceil(self.count/float(self.limit)))
        self.current_page = int(floor(self.offset / float(self.limit))) + 1

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

            except ValidationError as e:
                current_app.logger.error(e.message)

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

        except BuildError as e:
            current_app.logger.error('Pagination navigation could not be built. This might be fixable with more magic.')
            self.pagination = False



class Form(Renderable):

    name = None
    title = None
    fields = None
    rendered = None

    def __init__(self, name, title='', method='POST', action=None):
       
        self.name = name
        self.title = title
        self.method = method
        self.action = action
        self.fields = OrderedDict()
        self.render_reset()


    def add_field(self, name, field_type, value=None):
        self.fields[name] = (field_type, value)

    def render_reset(self):
        self.rendered = []


    def render_field(self, name):
        
        field_type, value = self.fields[name]

        tpls = ["fields/%s.jinja" % (field_type,)]
        tpls.append("fields/field.jinja")

        self.rendered.append(name)
        return render_template(tpls, field_type=field_type, value=value)


    def render_fields(self):
        
        rendered_fields = u''

        for name in self.fields.keys():

            if name not in self.rendered:
                rendered_fields += self.render_field(name)

        return rendered_fields
