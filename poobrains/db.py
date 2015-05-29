from math import ceil, floor
from flask import abort, url_for, current_app, request
from werkzeug.routing import BuildError
import peewee
from .rendering import ChildAware, Renderable, Menu

db_proxy = peewee.Proxy()


class BaseModel(peewee.Model, ChildAware):

    class Meta:
        database = db_proxy


    @classmethod
    def load(cls, id_or_name):

        try:
            if type(id_or_name) is int or (type(id_or_name) is unicode and id_or_name.isdigit()):
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



class Storable(BaseModel, Renderable):

    name = peewee.CharField()
    title = peewee.CharField()


class Listing(Renderable):

    cls = None
    offset = None
    limit = None
    items = None
    pagecount = None
    count = None
    pagination = None
    current_page = None

    def __init__(self, cls, offset=0, limit=None):

        super(Listing, self).__init__()

        self.cls = cls
        self.offset = offset

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

        for item in items:
            self.items.append(item)
       
        # Build pagination if matching endpoint and enough rows exist
        endpoint = request.endpoint
        print "WTF ENDPOINT: ", endpoint
        if not endpoint.endswith('_offset'):
            endpoint = '%s_offset' % (endpoint,)
        print "DEM  ENDPOINT", endpoint

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
            print "well, fuck", e
            self.pagination = False
