# -*- coding: utf-8 -*-

import collections
import datetime
import peewee
import flask
import poobrains


class Comment(poobrains.auth.Administerable):

    class Meta:

        abstract = False
        order_by = ['created']

    model = poobrains.storage.fields.CharField()
    handle = poobrains.storage.fields.CharField()
    reply_to = poobrains.storage.fields.ForeignKeyField('self', null=True)
    created = poobrains.storage.fields.DateTimeField(default=datetime.datetime.now, null=False)
    author = poobrains.storage.fields.CharField()
    text = poobrains.storage.fields.TextField()


    def thread(self):
        #TODO: Move creating trees into a stored procedure for performance at some point
        thread = collections.OrderedDict()

        children = Comment.select().where(Comment.reply_to == self)

        for child in children:
            thread[child] = child.thread()

        return thread

    def child_comments(self):
        return Comment.select().where(Comment.reply_to == self)


    def reply_form(self):
        return CommentForm(self.model, self.handle, reply_to=self)



class Commentable(poobrains.tagging.Taggable):

    class Meta:
        abstract = True

    comments = None
    comments_threaded = None

    def __init__(self, *args, **kwargs):

        super(Commentable, self).__init__(*args, **kwargs)
        self.comments = []
        self.comments_threaded = collections.OrderedDict()


    def prepared(self):
        
        self.comments = Comment.select().where(Comment.model == self.__class__.__name__, Comment.handle == self.handle_string)
        root_comments = Comment.select().where(Comment.model == self.__class__.__name__, Comment.handle == self.handle_string, Comment.reply_to == None)
        for comment in root_comments:
            self.comments_threaded[comment] = comment.thread()


    def comment_form(self, reply_to=None):

        return CommentForm(self.__class__.__name__, self.handle_string, reply_to=reply_to)


@poobrains.app.expose('/comment/<string:model>/<string:handle>')
@poobrains.app.expose('/comment/<string:model>/<string:handle>/<int:reply_to>')
class CommentForm(poobrains.form.Form):

    instance = None # Commentable instance the comment is going to be associated to
    reply_to = poobrains.form.fields.Value()
    author = poobrains.form.fields.Text(required=True)
    text = poobrains.form.fields.TextArea(required=True)
    submit = poobrains.form.Button('submit', label='Send comment')

    def __init__(self, model, handle, **kwargs):

        reply_to = kwargs.pop('reply_to') if kwargs.has_key('reply_to') else None
        if isinstance(reply_to, int):
            reply_to = Comment.load(reply_to)
        super(CommentForm, self).__init__(**kwargs)

        cls = Commentable.children_keyed()[model]
        instance = cls.load(handle)

        self.instance = instance
        self.reply_to.value = reply_to
        
        self.action = "/comment/%s/%s" % (self.instance.__class__.__name__, self.instance.handle_string) # FIXME: This is shit. Maybe we want to teach Pooprint.get_view_url handling extra parameters from the URL?
        if reply_to:
            self.action += "/%d" % reply_to.id


    def handle(self):

        self.instance.permissions['read'].check(flask.g.user)
        Comment.permissions['create'].check(flask.g.user)

        comment = Comment()
        comment.model = self.instance.__class__.__name__
        comment.handle = self.instance.handle_string
        comment.reply_to = self.fields['reply_to'].value
        comment.author = self.fields['author'].value
        comment.text = self.fields['text'].value

        try:
            comment.save()
            flask.flash("Comment saved!")
        except peewee.PeeweeException as e:
            flask.flash("Could not save your comment!", 'error')
            poobrains.app.logger.error("Could not save a comment. %s: %s" % (e.__class__.__name__, e.message))


        return flask.redirect(self.instance.url('full'))
