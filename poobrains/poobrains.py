# -*-  coding: utf-8 -*-

import os
import sys
import logging
from logging.handlers import WatchedFileHandler
from functools import wraps
from flask import Flask, Blueprint, current_app, request, g, abort, flash, redirect, url_for, send_from_directory
#from flask.signals import appcontext_pushed # TODO: needed?
from flask.helpers import locked_cached_property
from jinja2 import FileSystemLoader, DictLoader
from playhouse.db_url import connect
import peewee

from collections import OrderedDict

import storage
import auth
import cli
from rendering import Renderable, RenderString, Menu, render 
from helpers import TrueDict 
import defaults

try:
    import config # imports config relative to main project

except ImportError as e:

    print "Poobrains: This application has no config module. Just so you know…"
    config = False


def admin_menu():

    menu = Menu('main')
    menu.title = 'Administration'

    for storable in storage.Storable.children():
        try:
            menu.append(storable.url('teaser-edit'), storable.__name__)
        except Exception as e:
            flash("Can't create administration link for %s." % (storable.__name__,))
            #pass

    return menu

@render()
def admin_index():
    return admin_menu()


class ErrorPage(Renderable):

    error = None

    def __init__(self, message, status_code):

        super(ErrorPage, self).__init__()
        self.title = "Ermahgerd, %d!" % (status_code,)
        self.message = message



class Poobrain(Flask):

    site = None
    admin = None
    resource_extension_whitelist = None
    error_codes = {
        peewee.OperationalError: 500,
        peewee.IntegrityError: 400,
        peewee.DoesNotExist: 404
    }


    def __init__(self, *args, **kwargs):

        super(Poobrain, self).__init__(*args, **kwargs)

        if config:
            for name in dir(config):
                if name.isupper():
                    self.config[name] = getattr(config, name)

        for name in dir(defaults):
            if name.isupper and not self.config.has_key(name):
                self.config[name] = getattr(defaults, name)

        try:
            if self.config['LOGFILE']: # log to file, if configured
                log_handler = WatchedFileHandler(self.config['LOGFILE'])
                if self.debug:
                    log_handler.setLevel(logging.DEBUG)
                else:
                    log_handler.setLevel(logging.WARNING)

                self.logger.addHandler(log_handler)

        except IOError as e:
            import grp

            user = os.getlogin()
            group = grp.getgrgid(os.getgid()).gr_name
            sys.exit("Somethings' fucky with the log file: %s. Current user/group is %s/%s." % (e,user,group))

        self.logger.error('ZOMGAFTERLOG')



        self.site = Pooprint('site', 'site')
        self.admin = Pooprint('admin', 'admin')

        self.admin.box('menu_main')(admin_menu)

        self.poobrain_path = os.path.dirname(__file__)
        self.resource_extension_whitelist = ['css', 'png', 'svg', 'ttf', 'otf', 'js']


        self.db = connect(self.config['DATABASE'])
        storage.proxy.initialize(self.db)

        self.add_url_rule('/theme/<string:filename>', 'serve_theme_resources', self.serve_theme_resources)

        self.register_error_handler(404, self.errorpage)
        self.register_error_handler(peewee.OperationalError, self.errorpage)
        self.register_error_handler(peewee.IntegrityError, self.errorpage)
        self.register_error_handler(peewee.DoesNotExist, self.errorpage)

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
        if hasattr(error, 'code') and isinstance(error.code, int):
            status_code = error.code
        
        else:
            status_code = 500
            for cls, code in self.error_codes.iteritems():
                if isinstance(error, cls):
                    status_code = code
                    break


        return ErrorPage(error, status_code), status_code
    
    
    def serve_theme_resources(self, filename):

        self.logger.debug("I'm serving theme resource %s!" %(filename,))

        paths = []

        extension = filename.split('.')
        if len(extension) > 1:
            extension = extension[-1]

        else:
            abort(404)

        if extension not in self.resource_extension_whitelist:
            abort(404) # extension not allowed

        if self.config['THEME'] != 'default':
            paths.append(os.path.join(
                self.root_path, 'themes', self.config['THEME'],
                filename))

            paths.append(os.path.join(
                self.poobrain_path, 'themes', self.config['THEME'],
                filename))

        paths.append(os.path.join(
            self.root_path, 'themes', 'default',
            filename))

        paths.append(os.path.join(
            self.poobrain_path, 'themes', 'default',
            filename))

        for current_path in paths:
            if os.path.exists(current_path):
                return send_from_directory(os.path.dirname(current_path), os.path.basename(current_path))

        abort(404)


    def request_setup(self):

        g.boxes = {}
        self.db.connect()
        connection = self.db.get_conn()


    def request_teardown(self, exception):

        if not self.db.is_closed():
            self.db.close()


    def expose(self, rule, title=None):

        def decorator(cls):

            def admin_listing_actions():
                m = Menu('admin-listing-actions')
                m.append(cls.url('add'), 'add new %s' % (cls.__name__,))

                return m

            self.site.add_listing(cls, rule, title=title)
            self.site.add_view(cls, rule)
            self.admin.add_url_rule('/', 'index', admin_index)
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
                #self.logger.error("Failed generating URL for %s[%s]-%s. No matching route found." % (cls.__name__, id_or_name, mode))
                raise LookupError("Failed generating URL for %s[%s]-%s. No matching route found." % (cls.__name__, id_or_name, mode))


    def run(self, *args, **kw):

        if len(sys.argv) > 1 and sys.argv[1] == 'shell':
            shell = cli.Shell(config=self.config)
            shell.start()

        else:
            return super(Poobrain, self).run(*args, **kw)


class Pooprint(Blueprint):

    app = None
    db = None
    views = None
    listings = None
    boxes = None
    poobrain_path = None


    def __init__(self, *args, **kwargs):

        super(Pooprint, self).__init__(*args, **kwargs)

        self.views = {}
        self.listings = {}
        self.boxes = {}
        self.poobrain_path = os.path.dirname(__file__)
        
        self.before_request(self.box_setup)


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
            rule = os.path.join(rule, '<id_or_name>')

        # Why the fuck does HTML not support DELETE!?
        if mode in ('add', 'edit', 'delete'): 
            options['methods'] = ['GET', 'POST']
            if mode == 'delete':
                rule = os.path.join(rule, 'delete')
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
                                current_app.logger.error("Possible bug in default view_func catchall.")
                                current_app.logger.error('%s.%s' % (cls.__name__, field_name))

                    try:
                        instance.save()

                    except peewee.IntegrityError as e:
                        flash('Integrity error: %s' % e.message, 'error')

                        if mode == 'edit':
                            return redirect(cls.load(instance.id).url('edit'))

                        return redirect(self.get_url(cls, mode='teaser-edit'))

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

                else: # should only happen for 'add' mode
                    instance = cls()

                return instance


            endpoint = self.next_endpoint(cls, mode, 'view')


        if endpoint is None:
            endpoint = view_func.__name__

        self.add_url_rule(rule, endpoint, view_func, **options)
        self.views[cls][mode][endpoint] = primary


    def box_setup(self):
        
        for name, f in self.boxes.iteritems():
            g.boxes[name] = f()


    def add_listing(self, cls, rule, title=None, mode=None, endpoint=None, view_func=None, primary=False, action_func=None, **options):

        if not mode:
            mode = 'teaser'

        rule = os.path.join(rule, '') # make sure rule has trailing slash

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

                return storage.Listing(cls, offset=offset, title=title, mode=mode, actions=actions)

            endpoint = self.next_endpoint(cls, mode, 'listing')

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

                instance = storage.Listing(cls, title=title, offset=offset, mode=mode)
                return f(instance)

            self.add_listing(cls, rule, view_func=real, **options)

            return real

        return decorator


    def view(self, cls, rule, mode='full', primary=False, **options):
        # TODO: Why am I not using this in here? Change it - if that makes any sense.
        def decorator(f):

            @wraps(f)
            @render(mode)
            def real(id_or_name):

                instance = cls.load(id_or_name)
                return f(instance)

            self.add_view(cls, rule, view_func=real, mode=mode, primary=primary, **options)
            return real

        return decorator

    
    def box(self, name, ):

        def decorator(f):
            self.boxes[name] = f
            return f

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

    
    def next_endpoint(self, cls, mode, context):

            format = '%s_%s_%s_autogen_%%d' % (cls.__name__, context, mode)

            i = 1
            endpoint = format % (i,)
            endpoints = self.views[cls][mode].keys() if context == 'view' else self.listings[cls][mode].keys()
            while endpoint in endpoints:
                endpoint = format % (i,)
                i += 1

            return endpoint


    @locked_cached_property
    def jinja_loader(self):

        paths = []

        if self.app.config['THEME'] != 'default':
            paths.append(os.path.join(self.root_path, 'themes', self.app.config['THEME']))
            paths.append(os.path.join(self.poobrain_path, 'themes', self.app.config['THEME']))

        paths.append(os.path.join(self.root_path, 'themes', 'default'))
        paths.append(os.path.join(self.poobrain_path, 'themes', 'default'))

        return FileSystemLoader(paths)
