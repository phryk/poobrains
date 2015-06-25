# -*-  coding: utf-8 -*-

from os.path import join, exists, basename, dirname, isdir, isfile
from functools import wraps
from flask import Flask, Blueprint, current_app, request, g, abort, flash, redirect, url_for, send_from_directory
from flask.signals import appcontext_pushed
from flask.helpers import locked_cached_property
from jinja2 import FileSystemLoader, DictLoader
from playhouse.db_url import connect

from collections import OrderedDict
from .db import BaseModel, Listing, db_proxy
from .rendering import Renderable, RenderString, Menu, render 
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

        if config:
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


    def try_trigger_before_first_request_functions(self):

        # this function is the latest possible place to call @setupmethod functions
        if not self._got_first_request:
            self.register_blueprint(self.site)
            self.register_blueprint(self.admin, url_prefix='/admin')

        super(Poobrain, self).try_trigger_before_first_request_functions()


    @render('full')
    def errorpage(self, error):
        return ErrorPage(error), error.code
    
    
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


    def expose(self, rule, title=None):

        def decorator(cls):

            def admin_listing_actions():
                m = Menu('admin-listin-actions')
                m.append(cls.url('add'), 'add new %s' % (cls.__name__,))

                return m

            self.site.add_listing(cls, rule, title=title)
            self.site.add_view(cls, rule)
            self.admin.add_listing(cls, rule, title=title, mode='teaser-edit', action_func=admin_listing_actions)
            self.admin.add_view(cls, rule, mode='edit')
            self.admin.add_view(cls, rule, mode='delete')
            self.admin.add_view(cls, rule+'/add', mode='add')

            return cls

        return decorator

    
    def get_url(self, cls, id_or_name=None, mode=None):

        try:
            return self.site.get_url(cls, id_or_name=id_or_name, mode=mode)

        except LookupError:

            try: 
                return self.admin.get_url(cls, id_or_name=id_or_name, mode=mode)
            except LookupError:
                self.logger.error("Failed generating URL for %s[%s]-%s. No matching route found." % (cls.__name__, id_or_name, mode))
                return None



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

        if not self.views.has_key(cls):
            self.views[cls] = {}

        if not self.views[cls].has_key(mode):
            self.views[cls][mode] = TrueDict()

        if mode != 'add':
            rule = join(rule, '<id_or_name>')

        # Why the fuck does HTML not support DELETE!?
        if mode in ('add', 'edit', 'delete'): 
            options['methods'] = ['GET', 'POST']
            if mode == 'delete':
                rule = join(rule, 'delete')
                options['methods'].append('DELETE')

        if not view_func:
            @render(mode)
            def view_func(id_or_name=None):

                # handle POST for add and edit
                if mode in ('add', 'edit') and request.method == 'POST':

                    field_names = cls._meta.get_field_names()

                    if id_or_name:
                        instance = cls.load(id_or_name)
                    else:
                        instance = cls()

                    for field_name in field_names:
                        if not field_name in cls.field_blacklist:
                            try:
                                setattr(instance, field_name, request.form[field_name])
                            except Exception as e:
                                current_app.logger.error("Possible bug. default view_func catchall.")
                                current_app.logger.error('%s.%s' % (cls.__name__, field_name))

                    instance.save()

                    return redirect(self.get_url(cls, id_or_name=instance.name, mode='edit'))

                # Why the fuck does HTML not support DELETE!?
                elif mode == 'delete' and request.method in ('POST', 'DELETE') and id_or_name:
                    instance = cls.load(id_or_name)
                    message = "Deleted %s '%s'." % (cls.__name__, instance.name)
                    instance.delete_instance()
                    flash(message)
                    return redirect(cls.url('teaser-edit'))#HERE

                # handle 
                elif id_or_name:
                    instance = cls.load(id_or_name)
                    if mode in ('edit', 'delete'):
                        form = instance.form(mode)
                        form.actions = instance.actions

                        return form

                    return instance

                else: # should only happen for 'add' mode
                    instance = cls()
                    return instance.form('add')

            i = 1
            endpoint = '%s_view_%s_autogen_%d' % (cls.__name__, mode, i)
            while endpoint in self.views[cls][mode].keys():
                endpoint = '%s_view_%s_autogen_%d' % (cls.__name__, mode, i)
                i += 1

        if endpoint is None:
            endpoint = view_func.__name__

        self.add_url_rule(rule, endpoint, view_func, **options)
        self.views[cls][mode][endpoint] = primary


    def add_listing(self, cls, rule, title=None, mode=None, endpoint=None, view_func=None, primary=False, action_func=None, **options):

        if not mode:
            mode = 'teaser'

        rule = join(rule, '') # make sure rule has trailing slash

        if not self.listings.has_key(cls):
            self.listings[cls] = {}

        if not self.listings[cls].has_key(mode):
            self.listings[cls][mode] = TrueDict()

        if view_func is None:

            @render('full')
            def view_func(offset=0):

                if action_func:
                    actions = action_func()
                else:
                    actions = None

                return Listing(cls, offset=offset, title=title, mode=mode, actions=actions)

            #TODO: Document endpoint generation
            i = 1
            endpoint = '%s_listing_autogen_%d' % (cls.__name__, i)
            while endpoint in self.listings[cls][mode].keys():
                endpoint = '%s_listing_autogen_%d' % (cls.__name__, i)
                i += 1

        if endpoint is None:
            endpoint = view_func.__name__

        offset_rule = rule+'+<int:offset>'
        offset_endpoint = '%s_offset' % (endpoint,)

        self.add_url_rule(rule, endpoint=endpoint, view_func=view_func, **options)
        self.add_url_rule(offset_rule, endpoint=offset_endpoint, view_func=view_func, **options)

        self.listings[cls][mode][endpoint] = primary
    

    def listing(self, cls, rule, mode='teaser', title=None, **options):

        def decorator(f):

            @wraps(f)
            @render('full')
            def real(offset=0):

                instance = Listing(cls, title=title, offset=offset, mode=mode)
                return f(instance)

            self.add_listing(cls, rule, view_func=real, **options)

            return real

        return decorator


    def view(self, cls, rule, mode='full', primary=False, **options):

        def decorator(f):

            @wraps(f)
            @render(mode)
            def real(id_or_name):

                instance = cls.load(id_or_name)
                return f(instance)

            self.add_view(cls, rule, view_func=real, mode=mode, primary=primary, **options)
            return real

        return decorator




    def get_url(self, cls, id_or_name=None, mode=None):

        if mode == 'add' or (id_or_name and (mode is None or not mode.startswith('teaser'))):
            return self.get_view_url(cls, id_or_name, mode=mode)

        return self.get_listing_url(cls, mode=mode, id_or_name=id_or_name)


    def get_view_url(self, cls, id_or_name, mode=None):

        if mode == None:
            mode = 'full'

        if not self.views.has_key(cls):
            raise LookupError("No registered views for class %s." % (cls.__name__,))

        if not self.views[cls].has_key(mode):
            raise LookupError("No registered views for class %s with mode %s." % (cls.__name__, mode))


        endpoints = self.views[cls][mode]
       
        endpoint = endpoints.choose()
        endpoint = '%s.%s' % (self.name, endpoint)

        return url_for(endpoint, id_or_name=id_or_name)


    def get_listing_url(self, cls, mode=None, offset=0, id_or_name=None):

        if mode == None:
            mode = 'teaser'
        
        if id_or_name is not None:
            instance = cls.load(id_or_name)
            offset = cls.select().where(cls.id > instance.id).count()

        if not self.listings.has_key(cls):
            raise LookupError("No registered listings for class %s." % (cls.__name__,))

        if not self.listings[cls].has_key(mode):
            raise LookupError("No registered listings for class %s with mode %s." % (cls.__name__, mode))

        endpoints = self.listings[cls][mode]

        endpoint = endpoints.choose()
        endpoint = '%s.%s' % (self.name, endpoint)

        if isinstance(offset, int) and offset > 0:
            return url_for(endpoint+'_offset', offset=offset)

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


