from flask import abort, current_app
import peewee
from .rendering import ChildAware, Renderable

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
            print e
            print type(id_or_name), id_or_name
            #raise
            abort(404, "It is pitch black. You are likely to be eaten by a grue.")

        except peewee.OperationalError as e:
            print e
            abort(500, "Someone has set up us the bomb!")

        return instance



class Storable(BaseModel, Renderable):

    name = peewee.CharField()
    title = peewee.CharField()


class Listing(Renderable):

    cls = None
    offset = None
    limit = None
    items = None

    def __init__(self, cls, offset=0, limit=None):

        super(Listing, self).__init__()

        self.cls = cls
        self.offset = offset

        if limit is None:
            self.limit = current_app.config['PAGINATION_COUNT']
        else:
            self.limit = limit

        self.items = []
        items = cls.select().offset(self.offset).limit(self.limit)

        for item in items:
            self.items.append(item)
