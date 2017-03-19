# -*- coding: utf-8 -*-

from os import path
import collections
import peewee
import werkzeug
import flask
import poobrains

class UploadForm(poobrains.form.AddForm):
   
    upload = poobrains.form.fields.File()
    filename = poobrains.form.fields.Value()

    
    def __init__(self, *args, **kwargs):

        super(UploadForm, self).__init__(*args, **kwargs)

        if self.mode == 'add':
            self.fields['upload'].required = True


    def handle(self):

        poobrains.app.debugger.set_trace()
        upload_file = self.fields['upload'].value
        filename = werkzeug.utils.secure_filename(upload_file.filename)

        if filename is not '':

            self.fields['filename'].value = filename

            try:
                upload_file.save(path.join(self.instance.path, filename))

            except IOError as e:

                flask.flash("Failed saving file '%s'." % filename, 'error')
                poobrains.app.logger.error("Failed saving file: %s\n%s: %s" % (filename, type(e).__name__, e.message))
                return self # stop handling, show form within same request

        try:
            r = super(UploadForm, self).handle()

        except peewee.DatabaseError as e:
            flask.flash("Could not save file metadata for file '%s'. Deleting file, sorry if it was big. ¯\_(ツ)_/¯" % filename)
            poobrains.app.logger.error("Failed saving file metadata: %s\n%s: %s" % (filename, type(e).__name__, e.message))
            raise e

        return r


class File(poobrains.auth.NamedOwned):

    form_add = UploadForm
    form_edit = UploadForm
    path = None
    extension_whitelist = set(['*'])

    filename = poobrains.storage.fields.CharField()

    class Meta:

        modes = collections.OrderedDict([
            ('add', 'c'),
            ('teaser', 'r'),
            ('full', 'r'),
            ('raw', 'r'),
            ('inline', 'r'),
            ('edit', 'u'),
            ('delete', 'd')
        ])

    def __init__(self, *args, **kwargs):

        super(File, self).__init__(*args, **kwargs)
        self.path = path.join(poobrains.app.site_path, 'upload', self.__class__.__name__.lower())

    def __setattr__(self, name, value):

        if name == 'filename' and isinstance(value, basestring):
            value = werkzeug.utils.secure_filename(value)

        return super(File, self).__setattr__(name, value)

    @poobrains.auth.protected
    @poobrains.helpers.themed
    def view(self, mode=None, handle=None):

        if mode == 'raw':
            response = flask.send_from_directory(self.path, self.filename)
            response.headers['Content-Disposition'] = u'filename="%s"' % self.filename

            return response
        
        else:
            return poobrains.helpers.ThemedPassthrough(super(File, self).view(mode=mode, handle=handle)) # FIXME: themed and protected called twice


class Image(File):
    extension_whitelist = set(['gif', 'jpg', 'png', 'svg'])

class Audio(File):
    extension_whitelist = set(['mp3', 'flac', 'ogg', 'wav'])

class Video(File):
    extension_whitelist = set(['mp4', 'webm', 'ogg'])

# setup upload routes for "raw" mode

for cls in [File] + File.children():
    rule = path.join("/upload/", cls.__name__.lower())
    poobrains.app.site.add_view(cls, rule, mode='raw')
