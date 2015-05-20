from db import Storable
from peewee import CharField

class Content(Storable):
    title = CharField()
