# -*- coding: utf-8 -*-

import random
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
    comments_enabled = poobrains.storage.fields.BooleanField(default=0)

    def __init__(self, *args, **kwargs):

        super(Commentable, self).__init__(*args, **kwargs)
        self.comments = []
        self.comments_threaded = collections.OrderedDict()


    def prepared(self):
        
        super(Commentable, self).prepared()
      
        try:
            Comment.permissions['read'].check(flask.g.user)
            self.comments = Comment.select().where(Comment.model == self.__class__.__name__, Comment.handle == self.handle_string)
            root_comments = Comment.select().where(Comment.model == self.__class__.__name__, Comment.handle == self.handle_string, Comment.reply_to == None)
            for comment in root_comments:
                self.comments_threaded[comment] = comment.thread()

        except poobrains.auth.AccessDenied:
            pass # No point loading shit this user isn't allowed to render anyways.


    def comment_form(self, reply_to=None):

        try:
            Comment.permissions['create'].check(flask.g.user) # no form for users who aren't allowed to comment
            return CommentForm(self.__class__.__name__, self.handle_string, reply_to=reply_to)

        except poobrains.auth.AccessDenied:
            return poobrains.rendering.RenderString("You are not allowed to post comments.")



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
        self.fields['reply_to'].value = reply_to
        
        self.action = "/comment/%s/%s" % (self.instance.__class__.__name__, self.instance.handle_string) # FIXME: This is shit. Maybe we want to teach Pooprint.get_view_url handling extra parameters from the URL?
        if reply_to:
            self.action += "/%d" % reply_to.id


    def handle(self):

        poobrains.app.debugger.set_trace()
        self.instance.permissions['read'].check(flask.g.user)
#        Comment.permissions['create'].check(flask.g.user)
#
#        comment = Comment()
#        comment.model = self.instance.__class__.__name__
#        comment.handle = self.instance.handle_string
#        comment.reply_to = self.fields['reply_to'].value
#        comment.author = self.fields['author'].value
#        comment.text = self.fields['text'].value
#
#        try:
#            comment.save()
#            flask.flash("Comment saved!")
#        except peewee.PeeweeException as e:
#            flask.flash("Could not save your comment!", 'error')
#            poobrains.app.logger.error("Could not save a comment. %s: %s" % (e.__class__.__name__, e.message))
#
#        return flask.redirect(self.instance.url('full'))

        challenges = Challenge.select()
        if len(challenges):
            challenge = challenges[random.randint(0, len(challenges) - 1)] # I'm hoping this automatically adds a WHERE clause, consider this a FIXME if not
        else:
            flask.flash("I'm sorry Dave. I'm afraid I can't do that.")
            return flask.redirect(self.instance.url('full'))

        iteration_limit = 10
        for i in range(0, iteration_limit):
            name = poobrains.helpers.random_string_light(32).lower()
            if not Response.select().where(Response.name == name).count():
                break
            elif i == iteration_limit - 1: # means loop ran through without finding a free response name
                flask.flash("I'm sorry Dave. I'm afraid I can't do that.")
                return flask.redirect(self.instance.url('full'))

        response = Response()
        response.name = name
        response.challenge = challenge
        response.model = self.instance.__class__.__name__
        response.handle = self.instance.handle_string
        response.reply_to = self.fields['reply_to'].value
        response.author = self.fields['author'].value
        response.text = self.fields['text'].value

        response.save()
        return flask.redirect(response.url('full'))


class Challenge(poobrains.auth.Administerable):

    question = poobrains.storage.fields.CharField()
    answer = poobrains.storage.fields.CharField()


class Response(poobrains.storage.Named):

    title = "Comment challenge"
    challenge = poobrains.storage.fields.ForeignKeyField(Challenge)
    model = poobrains.storage.fields.CharField()
    handle = poobrains.storage.fields.CharField()
    reply_to = poobrains.storage.fields.ForeignKeyField('self', null=True)
    created = poobrains.storage.fields.DateTimeField(default=datetime.datetime.now, null=False)
    author = poobrains.storage.fields.CharField()
    text = poobrains.storage.fields.TextField()

    @poobrains.helpers.themed
    def view(self, mode=None, handle=None):

        """
        view function to be called in a flask request context
        """
        poobrains.app.debugger.set_trace()  
        return self


poobrains.app.site.add_view(Response, '/comment/challengeresponse/<handle>', mode='full')


class ResonseForm(poobrains.form.Form):

    response = poobrains.form.fields.Text(required=True)

    def __init__(self, response, **kwargs):
        self.response = 'foo'# TODO: Fuck it, going to go for captchas.


    def handle(self):

        #if ''.join(self.fields['response'].value.lower().split(' ')) == self.
        pass
