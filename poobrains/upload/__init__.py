# -*- coding: utf-8 -*-

from os import path
import collections
import werkzeug
import flask
import poobrains

class UploadForm(poobrains.form.AddForm):
   
    name = poobrains.form.fields.Value()
    upload = poobrains.form.fields.File()

    def handle(self):

        upload_file = self.fields['upload'].value
        filename = werkzeug.utils.secure_filename(upload_file.filename)
        upload_file.save(path.join(self.instance.path, filename))


        self.fields['name'].value = filename # we just want the filename in the db
        return super(UploadForm, self).handle()


class Upload(poobrains.auth.NamedOwned):

    form_add = UploadForm
    form_edit = UploadForm
    path = None
    extension_whitelist = set(['*'])

    class Meta:
        abstract = True
        modes = collections.OrderedDict([
            ('add', 'c'),
            ('raw', 'r'),
            ('teaser', 'r'),
            ('full', 'r'),
            ('edit', 'u'),
            ('delete', 'd')
        ])

    def __init__(self, *args, **kwargs):

        super(Upload, self).__init__(*args, **kwargs)
        self.path = path.join(poobrains.app.site_path, 'upload', self.__class__.__name__.lower())

    def __setattr__(self, name, value):

        if name == 'name':
            value = werkzeug.utils.secure_filename(value)

        return super(Upload, self).__setattr__(name, value)

    @poobrains.auth.protected
    @poobrains.helpers.themed
    def view(self, mode=None, handle=None):

        if mode == 'raw':
            return flask.send_from_directory(self.path, self.name)
        
        else:
            return poobrains.helpers.ThemedPassthrough(super(Upload, self).view(mode=mode, handle=handle)) # FIXME: themed and protected called twice


class Image(Upload):
    extension_whitelist = set(['gif', 'jpg', 'png', 'svg'])


# setup upload routes for "raw" mode

for cls in Upload.children():
    rule = path.join("/upload/", cls.__name__.lower())
    poobrains.app.site.add_view(cls, rule, mode='raw')
