# -*- coding: utf-8 -*-
import os
import random
import functools
import collections
import datetime
import peewee
import flask

import io
from PIL import Image, ImageDraw, ImageFont, ImageFilter

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

        children = Commentable.class_children_keyed()
        if children.has_key(self.model):

            model = Commentable.class_children_keyed()[self.model]
            comments_enabled = model.load(self.handle).select(model.comments_enabled).scalar()

            if comments_enabled:

                try:
                    self.permissions['create'].check(flask.g.user)
                    return CommentForm(self.model, self.handle, reply_to=self)

                except poobrains.auth.AccessDenied:
                    return False

            return poobrains.rendering.RenderString("Commenting is disabled.")

        raise Exception("Bork")


class Commentable(poobrains.tagging.Taggable):

    class Meta:
        abstract = True

    comments = None
    comments_threaded = None
    comments_enabled = poobrains.storage.fields.BooleanField(default=False)
    notify_owner = poobrains.storage.fields.BooleanField(default=False)

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

        if self.comments_enabled:

            try:
                Comment.permissions['create'].check(flask.g.user) # no form for users who aren't allowed to comment
                return CommentForm(self.__class__.__name__, self.handle_string, reply_to=reply_to)

            except poobrains.auth.AccessDenied:
                return poobrains.rendering.RenderString("You are not allowed to post comments.")

        return poobrains.rendering.RenderString("Commenting is disabled.")



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

        cls = Commentable.class_children_keyed()[model]
        instance = cls.load(handle)

        self.instance = instance
        self.fields['reply_to'].value = reply_to
        
        self.action = "/comment/%s/%s" % (self.instance.__class__.__name__, self.instance.handle_string) # FIXME: This is shit. Maybe we want to teach Pooprint.get_view_url handling extra parameters from the URL?
        if reply_to:
            self.action += "/%d" % reply_to.id


    def handle(self):

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

        iteration_limit = 10
        for i in range(0, iteration_limit):
            name = poobrains.helpers.random_string_light(16).lower()
            if not Challenge.select().where(Challenge.name == name).count():
                break
            elif i == iteration_limit - 1: # means loop ran through without finding a free challenge name
                flask.flash("I'm sorry Dave. I'm afraid I can't do that.")
                return flask.redirect(self.instance.url('full'))

        challenge = Challenge()
        challenge.name = name
        challenge.model = self.instance.__class__.__name__
        challenge.handle = self.instance.handle_string
        challenge.reply_to = self.fields['reply_to'].value
        challenge.author = self.fields['author'].value
        challenge.text = self.fields['text'].value

        challenge.save()

        return flask.redirect(challenge.url('full'))


class Challenge(poobrains.storage.Named):


    class Meta:

        modes = collections.OrderedDict([('full', 'read'), ('raw', 'read')])


    title = 'Fuck bots, get bugs'
    captcha = poobrains.storage.fields.CharField(default=functools.partial(poobrains.helpers.random_string_light, 6))
    model = poobrains.storage.fields.CharField()
    handle = poobrains.storage.fields.CharField()
    reply_to = poobrains.storage.fields.ForeignKeyField(Comment, null=True)
    created = poobrains.storage.fields.DateTimeField(default=datetime.datetime.now, null=False)
    author = poobrains.storage.fields.CharField()
    text = poobrains.storage.fields.TextField()


    def view(self, mode=None, handle=None):

        """
        view function to be called in a flask request context
        """

        if mode == 'raw':

#            colors = [
#                color.Color('#aaff00'),
#                color.Color('#ffaa00'),
#                color.Color('#ff00aa'),
#                color.Color('#aa00ff'),
#                color.Color('#99ffaa'),
#                color.Color('#00aaff')
#            ]
#
#            img = image.Image(width=210, height=70)
#            x_jitter = (-5, 5)
#            y_jitter = (-10, 10)
#
#            x = (img.width / 2) #+ random.randint(x_jitter[0], x_jitter[1])
#            y = (img.width / 2) #+ random.randint(y_jitter[0], y_jitter[1])
#            x = 10
#            y = 50
#            baseline = y
#
#            for char in self.captcha:
#
#                draw = drawing.Drawing()
#                draw.font = os.path.join(poobrains.app.poobrain_path, 'knewave-outline.otf')
#                c = colors[random.randint(0, len(colors) -1)]
#                draw.stroke_color = c
#                draw.fill_color = c
#                draw.font_size = 40
#                draw.translate(x, y)
#                draw.rotate(random.randint(-20, 20))
#                draw.text(0,0 , char)
#                draw(img)
#
#                x += 30 + random.randint(x_jitter[0], x_jitter[1])
#                y = baseline + random.randint(y_jitter[0], y_jitter[1])
#            fg = img.clone()    
#            img.gaussian_blur(3, 3)
#            img.composite(fg, left=0, top=0)

            colors = [
                (0,128,255),
                (0,255,128),
                (128,0,255),
                (128,255,0),
                (255,0,128),
                (255,128,0)
            ]

            font_path = os.path.join(poobrains.app.poobrain_path, 'themes/default/fonts/knewave/knewave-outline.otf')
            print "FLORB: ", font_path
            image = Image.new('RGBA', (250, 80), (255,255,255,0))
            font = ImageFont.truetype(font_path, 42)
            #font = ImageFont.truetype('Orbitron Medium.ttf', 40)


            #x_jitter = ((image.width/10) * -1, 0)
            #y_jitter = ((image.height/10) * -1, image.height/10)
            x_jitter = (-5, 5)
            y_jitter = (-5, 5)

            textsize = font.getsize(' '.join(self.captcha))
            print textsize
            centered = (image.width / 2 - textsize[0] / 2, image.height / 2 - textsize[1] / 2)

            x = centered[0] + random.randint(x_jitter[0], x_jitter[1])
            y = centered[1] + random.randint(y_jitter[0], y_jitter[1])
            baseline = centered[1]

            for char in self.captcha:

                c = colors[random.randint(0, len(colors) -1)]
                c = tuple(list(c) + [random.randint(255,255)])


                char_size = font.getsize(char)

                char_wrapped = ' %s ' % char
                char_wrapped_size = font.getsize(char_wrapped)

                char_layer = Image.new('RGBA', char_wrapped_size, (0,0,0,0))
                char_draw = ImageDraw.Draw(char_layer)

                char_draw.text((0,0), char_wrapped, c, font=font)
                char_layer = char_layer.rotate(random.randint(-15, 15), expand=True, resample=Image.BICUBIC)

                image.paste(
                    char_layer,
                    (x, y),
                    mask=char_layer,
                )

                x += char_size[0] + random.randint(x_jitter[0], x_jitter[1])
                y = baseline + random.randint(y_jitter[0], y_jitter[1])

            shine = image.filter(ImageFilter.GaussianBlur(radius=8))
            image = Image.alpha_composite(image, shine)

            out = io.BytesIO()
            image.save(out, format='PNG')

            return flask.Response(
                out.getvalue(),
                mimetype='image/png'
            )

        return ChallengeForm(self).view('full')

poobrains.app.site.add_view(Challenge, '/comment/challenge/<handle>/', mode='full')
poobrains.app.site.add_view(Challenge, '/comment/challenge/<handle>/raw', mode='raw')


class ChallengeForm(poobrains.form.Form):

    challenge = None
    response = poobrains.form.fields.Text()
    submit = poobrains.form.Button('submit', label='Send')

    def __init__(self, challenge):

        super(ChallengeForm, self).__init__()
        self.challenge = challenge


    def handle(self):

        if self.fields['response'].value == self.challenge.captcha:

            try:

                cls = Commentable.class_children_keyed()[self.challenge.model]
                instance = cls.load(self.challenge.handle)

            except KeyError:
                flask.flash("WRONG!1!!", 'error')
                return flask.redirect('/')

            except peewee.DoesNotExist:
                flask.flash("The thing you wanted to comment on does not exist anymore.")
                return flask.redirect(cls.url('teaser'))

            comment = Comment()
            comment.model = self.challenge.model
            comment.handle = self.challenge.handle
            comment.reply_to = self.challenge.reply_to
            comment.author = self.challenge.author
            comment.text = self.challenge.text

            if comment.save():
                flask.flash("Your comment has been saved.")

                if instance.notify_owner:
                    instance.owner.notify("New comment on [%s/%s] by %s." % (self.challenge.model, self.challenge.handle, self.challenge.author))
                
                self.challenge.delete_instance() # commit glorious seppuku
                return flask.redirect(instance.url('full'))

            flask.flash("Your comment could not be saved.", 'error')

        else:

            flask.flash("WRONG.", 'error')
            self.challenge.captcha = self.challenge.__class__.captcha.default()
            self.challenge.save()
            return flask.redirect(self.challenge.url('full'))
