# -*-  coding: utf-8 -*-

from os.path import join, exists, basename, dirname, isdir, isfile
from flask import Flask, g, abort, send_from_directory
from flask.helpers import locked_cached_property
from jinja2 import FileSystemLoader
from playhouse.db_url import connect

from .db import BaseModel, db_proxy
from .rendering import Renderable, view
import defaults

try:
    import config

except ImportError as e:

    print "Poobrains: This application has no config module. Just so you know…"
    config = False


class ErrorPage(Renderable):

    error = None

    def __init__(self, error):

        super(ErrorPage, self).__init__()
        self.title = "Ermahgerd, %d!" % (error.code,)
        self.error = error



class Poobrain(Flask):

    db = None
    boxes = None
    poobrain_path = None
    resource_extension_whitelist = None

    def __init__(self, *args, **kwargs):

        super(Poobrain, self).__init__(*args, **kwargs)

        self.boxes = {}
        self.poobrain_path = dirname(__file__)
        self.resource_extension_whitelist = ['css', 'png', 'svg', 'ttf', 'otf', 'js']

        if config is not False:
            for name in dir(config):
                if name.isupper():
                    self.config[name] = getattr(config, name)

        for name in dir(defaults):
            if name.isupper and not self.config.has_key(name):
                self.config[name] = getattr(defaults, name)

        self.db = connect(self.config['DATABASE'])
        db_proxy.initialize(self.db)

        self.add_url_rule('/theme/<string:filename>', 'Poobrain.serve_theme_resources', self.serve_theme_resources)

        if self.config['MAY_INSTALL']:
            self.add_url_rule('/install', 'Poobrain.install', self.install)


        # Make sure that each request has a proper database connection
        self.before_request(self.request_setup)
        self.teardown_request(self.request_teardown)

        self.error_handler_spec[None][404] = self.errorpage
        self.error_handler_spec[None][500] = self.errorpage

    @view
    def errorpage(self, error):
        return ErrorPage(error)


    def listroute(self, rule, **options):

        offset_rule = join(rule, '<int:offset>/')

        def decorator(f):

            #endpoint = options.pop('endpoint', None)
            endpoint = f.__name__
            offset_endpoint = '%s_offset' % (f.__name__,)
            self.add_url_rule(rule, endpoint, f, **options)
            self.add_url_rule(offset_rule, offset_endpoint, f, **options)

            return f

        return decorator


    def install(self):

        self.db.create_tables(BaseModel.children())
        return "Installation procedure complete."


    def serve_theme_resources(self, filename):

        paths = []

        extension = filename.split('.')
        if len(extension) > 1:
            extension = extension[-1]

        else:
            abort(404)

        if extension not in self.resource_extension_whitelist:
            abort(404) # extension not allowed

        if self.config['THEME'] != 'default':
            paths.append(join(
                self.root_path, 'themes', self.config['THEME'],
                filename))

            paths.append(join(
                self.poobrain_path, 'themes', self.config['THEME'],
                filename))

        paths.append(join(
            self.root_path, 'themes', 'default',
            filename))

        paths.append(join(
            self.poobrain_path, 'themes', 'default',
            filename))

        for path in paths:
            if exists(path):
                return send_from_directory(dirname(path), basename(path))

        abort(404)


    def request_setup(self):

        self.db.connect()
        self.build_boxes()


    def request_teardown(self, exception):

        if not self.db.is_closed():
            self.db.close()


    def build_boxes(self):

        g.boxes = {}
        for name, f in self.boxes.iteritems():
            g.boxes[name] = f()
    
    
    @locked_cached_property
    def jinja_loader(self):

        paths = []

        if self.config['THEME'] != 'default':
            paths.append(join(self.root_path, 'themes', self.config['THEME']))
            paths.append(join(self.poobrain_path, 'themes', self.config['THEME']))

        paths.append(join(self.root_path, 'themes', 'default'))
        paths.append(join(self.poobrain_path, 'themes', 'default'))

        return FileSystemLoader(paths)


    def box(self, name):

        def decorator(f):
            self.boxes[name] = f
            return f

        return decorator
