import peewee

db_proxy = peewee.Proxy()


class BaseModel(peewee.Model):

    class Meta:
        database = db_proxy
