import peewee

db_proxy = peewee.Proxy()


class BaseModel(peewee.Model):

    class Meta:
        database = db_proxy


    @classmethod
    def children(cls):

        children = cls.__subclasses__()

        if len(children):
            for child in children:
                grandchildren = child.children()

            for grandchild in grandchildren:
                children.append(grandchild)

        return children
