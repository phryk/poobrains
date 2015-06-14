# -*- coding: utf-8 -*-

from math import ceil, floor
from re import match
from flask import abort, url_for, current_app, request
from werkzeug.routing import BuildError
import peewee
from .rendering import ChildAware, Renderable, Menu

db_proxy = peewee.Proxy()


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
        self.url = self.instance_url # hack to make .url callable for class and instances


    def __setattr__(self, name, value):

        if name == 'name' and not match('^[a-zA-ZäÄöÖüÜ_\-]*$', value):
            raise ValueError("Invalid value for name: %s" % (value,))

        super(Storable, self).__setattr__(name, value)


    @classmethod
    def load(cls, id_or_name):

        try:
            if type(id_or_name) is int or (isinstance(id_or_name, basestring) and id_or_name.isdigit()):
                instance = cls.get(cls.id == id_or_name)

            else:
                instance = cls.get(cls.name == id_or_name)

        except cls.DoesNotExist as e:
            abort(404, "It is pitch black. You are likely to be eaten by a grue.")

        except peewee.OperationalError as e:
            if current_app.debug:
                raise

            abort(500, "Somebody set up us the bomb.")

        return instance


    @classmethod
    def url(cls):
        return current_app.get_url(cls)


    def instance_url(self, mode=None):
        return current_app.get_url(self.__class__, id_or_name=self.name, mode=mode)


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

            except ValueError as e:
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
            current_app.logger.debug('Pagination navigation could not be built. This might be fixable with more magic.')
            self.pagination = False



class Form(Renderable):

    rendered = None

    def __init__(self, model_or_instance):

        self.render_reset()

        if isinstance(BaseModel, model_or_instance):
            model = model_or_instance.__class__
            instance = model_or_instance

        else:
            model = model_or_instance
            instance = None

        #TODO: add Storable.form() for class and instance


    def render_reset(self):
        self.rendered = []


    def render_field(self, name):
        pass


    def render_fields(self):
        pass
