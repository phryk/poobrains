# -*-  coding: utf-8 -*-

from os.path import join, exists, basename, dirname, isdir, isfile
from functools import wraps
from flask import Flask, Blueprint, current_app, g, abort, url_for, send_from_directory
from flask.helpers import locked_cached_property
from jinja2 import FileSystemLoader
from playhouse.db_url import connect

from collections import OrderedDict
from .db import BaseModel, Listing, db_proxy
from .rendering import Renderable, render 
from .helpers import TrueDict 
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

    site = None
    admin = None
    boxes = None
    resource_extension_whitelist = None


    def __init__(self, *args, **kwargs):

        super(Poobrain, self).__init__(*args, **kwargs)

        self.site = Pooprint('site', 'site')
        self.admin = Pooprint('admin', 'admin')
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

        self.add_url_rule('/theme/<string:filename>', 'serve_theme_resources', self.serve_theme_resources)

        if self.config['MAY_INSTALL']:
            self.add_url_rule('/install', 'Poobrain.install', self.install)

        self.error_handler_spec[None][403] = self.errorpage
        self.error_handler_spec[None][404] = self.errorpage
        self.error_handler_spec[None][500] = self.errorpage

        # Make sure that each request has a proper database connection
        self.before_request(self.request_setup)
        self.teardown_request(self.request_teardown)



    @render
    def errorpage(self, error):
        return ErrorPage(error)
    
    
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

        g.boxes = {}
        for name, f in self.boxes.iteritems():
            g.boxes[name] = f()


    def request_teardown(self, exception):

        if not self.db.is_closed():
            self.db.close()


    def box(self, name):

        def decorator(f):
            self.boxes[name] = f
            return f

        return decorator


    def run(self, *args, **kwargs):

        self.register_blueprint(self.site)
        self.register_blueprint(self.admin, url_prefix='/admin')

        super(Poobrain, self).run(*args, **kwargs)



class Pooprint(Blueprint):

    app = None
    db = None
    views = None
    listings = None
    poobrain_path = None


    def __init__(self, *args, **kwargs):

        super(Pooprint, self).__init__(*args, **kwargs)

        self.views = {}
        self.listings = {}
        self.poobrain_path = dirname(__file__)


    def register(self, app, options, first_registration=False):

        super(Pooprint, self).register(app, options, first_registration=first_registration)
        
        self.app = app
        self.db = app.db


    def add_view(self, cls, rule, endpoint=None, view_func=None, mode='full', primary=False, **options):

        rule = join(rule, '<id_or_name>')
        if not self.views.has_key(cls):
            self.views[cls] = TrueDict()
        
        if view_func is None:

            @render
            def view_func(id_or_name):
                
                return cls.load(id_or_name)

            i = 1
            endpoint = '%s_view_autogen_%d' % (cls.__name__, i)
            while endpoint in self.views[cls].keys():
                endpoint = '%s_view_autogen_%d' % (cls.__name__, i)
                i += 1


        if endpoint is None:
            endpoint = view_func.__name__

        self.add_url_rule(rule, endpoint, view_func, **options)
        self.views[cls][endpoint] = primary


    def add_listing(self, cls, rule, endpoint=None, view_func=None, primary=False, **options):
    
        if not self.listings.has_key(cls):
            self.listings[cls] = TrueDict()

        if view_func is None:

            @render
            def view_func(offset=0):

                return Listing(cls, offset)

            i = 1
            endpoint = '%s_listing_autogen_%d' % (cls.__name__, i)
            while endpoint in self.listings[cls].keys():
                endpoint = '%s_listing_autogen_%d' % (cls.__name__, i)
                i += 1

        if endpoint is None:
            endpoint = view_func.__name__

        offset_rule = join(rule, '<int:offset>/')
        offset_endpoint = '%s_offset' % (endpoint,)

        self.add_url_rule(rule, endpoint=endpoint, view_func=view_func, **options)
        self.add_url_rule(offset_rule, endpoint=offset_endpoint, view_func=view_func, **options)

        self.listings[cls][endpoint] = primary
    

    def listing(self, cls, rule, **options):

        def decorator(f):

            @wraps(f)
            @render
            def real(offset=0):

                instance = Listing(cls, offset)
                return f(instance)

            self.add_listing(cls, rule, view_func=real, **options)

            return real

        return decorator


    def view(self, cls, rule, mode='full', primary=False, **options):

        def decorator(f):

            @wraps(f)
            @render
            def real(id_or_name):

                instance = cls.load(id_or_name)
                return f(instance)

            self.add_view(cls, rule, view_func=real, mode=mode, primary=primary, **options)
            return real

        return decorator


    def expose(self, rule):

        def decorator(cls):

            self.add_listing(cls, rule)
            self.add_view(cls, rule)

            return cls

        return decorator


    def get_url(self, cls, id_or_name=None):

        if id_or_name:
            if not self.views.has_key(cls):
                if current_app.debug:
                    raise LookupError("No registered views for class %s." % (cls.__name__,))
                return ''

            endpoints = self.views[cls]
        else:

            if not self.listings.has_key(cls):
                if current_app.debug:
                    raise LookupError("No registered listings for class %s." % (cls.__name__,))

            endpoints = self.listings[cls]

        if True in endpoints.values():
            for endpoint, primary in endpoints.iteritems():
                if primary == True:
                    break
        else:
            endpoint = endpoints.keys()[0]

        endpoint = '%s.%s' % (self.name, endpoint)
        if id_or_name:
            return url_for(endpoint, id_or_name=id_or_name)

        return url_for(endpoint)


    @locked_cached_property
    def jinja_loader(self):

        paths = []

        if self.app.config['THEME'] != 'default':
            paths.append(join(self.root_path, 'themes', self.app.config['THEME']))
            paths.append(join(self.poobrain_path, 'themes', self.app.config['THEME']))

        paths.append(join(self.root_path, 'themes', 'default'))
        paths.append(join(self.poobrain_path, 'themes', 'default'))

        return FileSystemLoader(paths)
