from flask import abort
import peewee
from .rendering import Renderable

db_proxy = peewee.Proxy()


class BaseModel(peewee.Model):

    class Meta:
        database = db_proxy


    @classmethod
    def load(cls, id_or_name):

        try:
            if type(id_or_name) is int or (type(id_or_name) is unicode and id_or_name.isdigit()):
                instance = cls.get(cls.id == id_or_name)

            else:
                instance = cls.get(cls.name == id_or_name)

        except Exception as e:
            print e
            print type(id_or_name), id_or_name
            abort(500, 'ZOMG')

        return instance


    @classmethod
    def children(cls):

        children = cls.__subclasses__()

        if len(children):
            for child in children:
                grandchildren = child.children()

            for grandchild in grandchildren:
                children.append(grandchild)

        return children


class Storable(BaseModel, Renderable):
    pass
