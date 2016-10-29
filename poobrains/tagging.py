# -*- coding: utf-8 -*-

import peewee

import poobrains

class Tag(poobrains.auth.Named):

    description = poobrains.storage.fields.TextField()
    parent = poobrains.storage.fields.ForeignKeyField('self', null=True, constraints=[peewee.Check('parent_id <> id')])


class TagBinding(poobrains.auth.Administerable):

    tag = poobrains.storage.fields.ForeignKeyField(Tag, related_name='_bindings')
    model = poobrains.storage.fields.CharField()
    handle = poobrains.storage.fields.CharField()
    priority = poobrains.storage.fields.IntegerField()
