# -*- coding: utf-8 -*-

import poobrains


class Comment(poobrains.auth.Administerable):

    class Meta:

        abstract = False
        order_by = ['created']

    model = poobrains.storage.fields.CharField()
    handle = poobrains.storage.fields.CharField()
    reply_to = poobrains.storage.fields.ForeignKeyField('self')
    created = poobrains.storage.fields.DateTimeField()
    author = poobrains.storage.fields.CharField()
    text = poobrains.storage.fields.TextField()


class Commentable(poobrains.tagging.Taggable):

    comments = None

    def __init__(self, *args, **kwargs):

        super(Commentable, self).__init__(*args, **kwargs)
        self.comments = []


    def prepared(self):
        
        self.comments = Comment.select().where(Comment.model == self.__class__.__name__, Comment.handle == self.handle_string)
