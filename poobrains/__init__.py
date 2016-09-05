# -*-  coding: utf-8 -*-

import os
import sys
import logging
import werkzeug
import flask
import collections
import functools

#from flask.signals import appcontext_pushed # TODO: needed?
import jinja2
from playhouse import db_url
import peewee


# internal imports
import helpers
import defaults

try:
    import config # imports config relative to main project


except ImportError as e:

    print "Poobrains: This application has no config module. Just so you know…"
    config = False


class FormDataParser(werkzeug.formparser.FormDataParser):
    
    def parse(self, *args, **kwargs):

        stream, form_flat, files_flat = super(FormDataParser, self).parse(*args, **kwargs)
        form = werkzeug.datastructures.MultiDict()

        for key, values in form_flat.iteritems():

            current = form
            segments = key.split('.')

            for segment in segments[:-1]:
                if not current.has_key(segment):
                    current[segment] = werkzeug.datastructures.MultiDict()

                current = current[segment]

            current[segments[-1]] = values

        if form_flat.has_key('submit'):
            current = form
            segments = form_flat['submit'].split('.')

            for segment in segments[:-1]:
                if not current.has_key(segment):
                    current[segment] = werkzeug.datastructures.MultiDict()

                current = current[segment]

            current[segments[-1]] = True

        # TODO: Make form ImmutableDict again?

        #if app.debug:
        #    app.debugger.set_trace()

        return (stream, form, files_flat)


class Request(flask.Request):

    form_data_parser_class = FormDataParser



class Poobrain(flask.Flask):

    request_class = Request
    debugger = None

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
                log_handler = logging.handlers.WatchedFileHandler(self.config['LOGFILE'])
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

        if self.debug:
            # show SQL queries
            peeweelog = logging.getLogger('peewee')
            peeweelog.setLevel(logging.DEBUG)
            peeweelog.addHandler(logging.StreamHandler())

            try:

                import signal
                import pudb
                if hasattr(signal, 'SIGINFO'):
                    pudb.set_interrupt_handler(signal.SIGINFO)
                    print "%s: a graphical debugger can be invoked with SIGINFO (^T)" % (self.name.upper())

                self.debugger = pudb

            except ImportError:
                print "pudb not installed, falling back to pdb!"

                import signal # shouldn't be needed but feels hacky to leave out
                import pdb
                if hasattr(signal, 'SIGINFO'):
                    pdb.set_interrupt_handler(signal.SIGINFO)


        self.poobrain_path = os.path.dirname(__file__)
        self.resource_extension_whitelist = ['css', 'png', 'svg', 'ttf', 'otf', 'js']

        self.db = db_url.connect(self.config['DATABASE'])

        self.add_url_rule('/theme/<string:filename>', 'serve_theme_resources', self.serve_theme_resources)

        # Make sure that each request has a proper database connection
        self.before_request(self.request_setup)
        self.teardown_request(self.request_teardown)


        # set up site and admin blueprints
        self.site = Pooprint('site', 'site')

        self.admin = Pooprint('admin', 'admin')


    def select_jinja_autoescape(self, filename):
        if filename is None:
            return super(Poobrain, self).select_jinja_autoescape(filename)
        return not filename.endswith(('.safe')) # Don't even know if I ever want to use .safe files, but hey, it's there.


    def try_trigger_before_first_request_functions(self):

        # this function is the latest possible place to call @setupmethod functions
        if not self._got_first_request:

            for (key, cls) in auth.Administerable.children_keyed().iteritems():
                
                rule = '%s/' % key.lower()
                actions = functools.partial(auth.admin_listing_actions, cls)

                self.admin.add_listing(cls, rule, title=cls.__name__, mode='teaser', action_func=actions, force_secure=True)
                self.admin.add_view(cls, rule, mode='edit', force_secure=True)
                self.admin.add_view(cls, rule, mode='delete', force_secure=True)
                self.admin.add_view(cls, '%sadd/' % rule, mode='add', force_secure=True)

                for field in cls._meta.reverse_rel.itervalues(): # Add Models that are associated by ForeignKeyField, like /user/foo/userpermissions
                    related_model = field.model_class

                    if issubclass(related_model, poobrains.auth.Administerable):

                        endpoint = "%s_%s" % (cls.__name__, related_model.__name__)
                        
                        #def view_func = functools.partial(cls.related_form, related_field=field)
                        #print "view_func:", view_func


                        def view_func(cls, field, handle):

                            related_model = field.model_class
                            instance = cls.load(cls.string_handle(handle))

                            if hasattr(related_model, 'related_form'):
                                form_class = related_model.related_form
                            else:
                                form_class = functools.partial(poobrains.auth.RelatedForm, related_model) # TODO: does this even work? and more importantly, is it even needed?

                            f = form_class(field, instance)
                            
                            return f.view('full')


                        self.admin.add_url_rule("%s<handle>/%s/" % (rule, related_model.__name__.lower()), endpoint, functools.partial(view_func, cls=cls, field=field), methods=['GET', 'POST'])

            self.register_blueprint(self.site)
            self.register_blueprint(self.admin, url_prefix='/admin/')

        super(Poobrain, self).try_trigger_before_first_request_functions()


    
    
    def serve_theme_resources(self, filename):

        paths = []

        extension = filename.split('.')
        if len(extension) > 1:
            extension = extension[-1]

        else:
            flask.abort(404)

        if extension not in self.resource_extension_whitelist:
            flask.abort(404) # extension not allowed

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
                return flask.send_from_directory(os.path.dirname(current_path), os.path.basename(current_path))

        flask.abort(404)


    def request_setup(self):

        flask.g.boxes = {}
        flask.g.forms = {}
        self.db.connect()
        connection = self.db.get_conn()

        flask.g.user = None
        if flask.request.environ['SSL_CLIENT_VERIFY'] == 'SUCCESS':

            try:
                cert_info = auth.ClientCert.get(auth.ClientCert.subject_name == flask.request.environ['SSL_CLIENT_S_DN'])
                flask.g.user = cert_info.user

            except auth.ClientCert.DoesNotExist:
                self.logger.error("httpd verified client certificate successfully, but it's not known at this site. certificate subject distinguished name is: %s" % flask.request.environ['SSL_CLIENT_S_DN'])

        if flask.g.user == None:
            try:
                flask.g.user = auth.User.load(1) # loads "Anonymous".
            except:
                pass

#        self.logger.debug(dir(flask.g.user))
#        self.logger.debug(flask.g.user)


    def request_teardown(self, exception):

        if not self.db.is_closed():
            self.db.close()


    def expose(self, rule, mode=None, title=None, force_secure=False):

        def decorator(cls):

            if issubclass(cls, storage.Storable):

                self.site.add_listing(cls, rule, mode='teaser', title=title, force_secure=force_secure)
                self.site.add_view(cls, rule, mode=mode, force_secure=force_secure)

            elif issubclass(cls, form.Form):

                self.site.add_view(cls, rule, force_secure=force_secure)

            return cls

        return decorator

    
    def get_url(self, cls, handle=None, mode=None):

        try:
            #TODO: Is it wise to just prefer self.site?
            return self.site.get_url(cls, handle=handle, mode=mode)

        except LookupError:

            try: 
                return self.admin.get_url(cls, handle=handle, mode=mode)
            except LookupError:
                #self.logger.error("Failed generating URL for %s[%s]-%s. No matching route found." % (cls.__name__, handle, mode))
                raise LookupError("Failed generating URL for %s[%s]-%s. No matching route found." % (cls.__name__, handle, mode))


    def run(self, *args, **kw):

        if len(sys.argv) > 1 and sys.argv[1] == 'shell':
            shell = poobrains.cli.Shell(config=self.config)
            shell.start()

        else:
            return super(Poobrain, self).run(*args, **kw)


class Pooprint(flask.Blueprint):

    app = None
    db = None
    views = None
    listings = None
    boxes = None
    poobrain_path = None


    def __init__(self, *args, **kwargs):

        super(Pooprint, self).__init__(*args, **kwargs)

        self.views = {}
        self.listings = {} # TODO: list of dicts? {primary: bool, endpoint: str}
        self.boxes = {}
        self.poobrain_path = os.path.dirname(__file__)
        
        self.before_request(self.box_setup)


    def register(self, app, options, first_registration=False):

        super(Pooprint, self).register(app, options, first_registration=first_registration)
        
        self.app = app
        self.db = app.db


    def add_view(self, cls, rule, endpoint=None, view_func=None, mode=None, primary=False, force_secure=False, **options):

        if not self.views.has_key(cls):
            self.views[cls] = collections.OrderedDict()

        if not self.views[cls].has_key(mode):
            self.views[cls][mode] = collections.OrderedDict()

        if mode != 'add' and issubclass(cls, poobrains.storage.Storable): # excludes adding and non-Storable Renderables like Forms
            rule = os.path.join(rule, '<handle>/')

        # Why the fuck does HTML not support DELETE!?
        options['methods'] = ['GET', 'POST']
        if mode == 'delete':
            rule = os.path.join(rule, 'delete')
            options['methods'].append('DELETE')

        #@poobrains.helpers.themed(mode)
        #@poobrains.helpers.access(getattr(cls, perm_names[mode]))
        #def view_func(handle=None):
        #    
        #    instance = cls.load(cls.string_handle(handle))
        #    return instance.view(mode)

        view_func = functools.partial(cls.class_view, mode)


#        if force_secure:
#            view_func = helpers.is_secure(view_func) # manual decoration, cause I don't know how to do this cleaner

        endpoint = self.next_endpoint(cls, mode, 'view')

        if endpoint is None: # TODO: does this even happen? kill it if not.
            endpoint = view_func.__name__

        self.add_url_rule(rule, endpoint, view_func, **options)
        self.views[cls][mode][endpoint] = {'primary': primary, 'endpoint': endpoint}


    def box_setup(self):
        
        for name, f in self.boxes.iteritems():
            flask.g.boxes[name] = f()


    def add_listing(self, cls, rule, title=None, mode=None, endpoint=None, view_func=None, primary=False, action_func=None, force_secure=False, **options):

        if not mode:
            mode = 'teaser'

        rule = os.path.join(rule, '') # make sure rule has trailing slash

        if not self.listings.has_key(cls):
            self.listings[cls] = {}

        if not self.listings[cls].has_key(mode):
            self.listings[cls][mode] = collections.OrderedDict()

        if view_func is None:

            @poobrains.helpers.themed
            def view_func(offset=0):

                if action_func:
                    actions = action_func()
                else:
                    actions = None

                return poobrains.storage.Listing(cls, offset=offset, title=title, mode=mode, actions=actions)

            endpoint = self.next_endpoint(cls, mode, 'listing')

        if force_secure:
            view_func = helpers.is_secure(view_func) # manual decoration, cause I don't know how to do this cleaner

        if endpoint is None:
            endpoint = view_func.__name__

        offset_rule = rule+'+<int:offset>'
        offset_endpoint = '%s_offset' % (endpoint,)

        self.add_url_rule(rule, endpoint=endpoint, view_func=view_func, **options)
        self.add_url_rule(offset_rule, endpoint=offset_endpoint, view_func=view_func, **options)

        self.listings[cls][mode][endpoint] = {'primary': primary, 'endpoint': endpoint}
    

    def listing(self, cls, rule, mode='teaser', title=None, **options):
        # TODO: Is this even used? Does keeping it make sense?
        def decorator(f):

            @functools.wraps(f)
            @poobrains.helpers.themed
            def real(offset=0):

                instance = poobrains.storage.Listing(cls, title=title, offset=offset, mode=mode)
                return f(instance)

            self.add_listing(cls, rule, view_func=real, **options)

            return real

        return decorator


#    def view(self, cls, rule, mode=None, primary=False, **options):
#        # TODO: Why am I not using this in here? Change that - if it makes any sense.
#        def decorator(f):
#
#            @functools.wraps(f)
#            @poobrains.helpers.themed
#            def real(handle):
#
#                instance = cls.load(cls.string_handle(handle))
#                return f(instance)
#
#            self.add_view(cls, rule, view_func=real, mode=mode, primary=primary, **options)
#            return real
#
#        return decorator

    
    def box(self, name):

        def decorator(f):
            self.boxes[name] = f
            return f

        return decorator


    def get_url(self, cls, handle=None, mode=None):

        if mode == 'add' or (handle and (mode is None or not mode.startswith('teaser'))):
            return self.get_view_url(cls, handle, mode=mode)

        return self.get_listing_url(cls, mode=mode, handle=handle)


    def get_view_url(self, cls, handle, mode=None):

        if mode == None:
            mode = 'full'

        if not self.views.has_key(cls):
            raise LookupError("No registered views for class %s." % (cls.__name__,))

        if not self.views[cls].has_key(mode):
            raise LookupError("No registered views for class %s with mode %s." % (cls.__name__, mode))


        endpoints = self.views[cls][mode]
       
        endpoint = helpers.choose_primary(endpoints)['endpoint']
        endpoint = '%s.%s' % (self.name, endpoint)

        return flask.url_for(endpoint, handle=handle)


    def get_listing_url(self, cls, mode=None, offset=0, handle=None):

        if mode == None:
            mode = 'teaser'
        
        if handle is not None:
            
            instance = cls.load(handle)

            clauses = []
            for order_field in cls._meta.order_by:
                #clauses.append(order_field > getattr(instance, order_field.name))
                if order_field._ordering == 'ASC':
                    clauses.append(instance._meta.fields[order_field.name] <= getattr(instance, order_field.name))
                else: # We'll just assume there can only be ASC and DESC
                    clauses.append(instance._meta.fields[order_field.name] >= getattr(instance, order_field.name))

            #clause = 

            offset = cls.select().where(*clauses).count() - 1

        if not self.listings.has_key(cls):
            raise LookupError("No registered listings for class %s." % (cls.__name__,))

        if not self.listings[cls].has_key(mode):
            raise LookupError("No registered listings for class %s with mode %s." % (cls.__name__, mode))

        endpoints = self.listings[cls][mode]

        #endpoint = endpoints.choose()
        endpoint = helpers.choose_primary(endpoints)['endpoint']
        endpoint = '%s.%s' % (self.name, endpoint)

        if isinstance(offset, int) and offset > 0:
            return flask.url_for(endpoint+'_offset', offset=offset)

        return flask.url_for(endpoint)

    
    def next_endpoint(self, cls, mode, context):

            format = '%s_%s_%s_autogen_%%d' % (cls.__name__, context, mode)

            i = 1
            endpoint = format % (i,)
            endpoints = self.views[cls][mode].keys() if context == 'view' else self.listings[cls][mode].keys()
            while endpoint in endpoints:
                endpoint = format % (i,)
                i += 1

            return endpoint


    @flask.helpers.locked_cached_property
    def jinja_loader(self):

        paths = []

        if self.app.config['THEME'] != 'default':
            paths.append(os.path.join(self.root_path, 'themes', self.app.config['THEME']))
            paths.append(os.path.join(self.poobrain_path, 'themes', self.app.config['THEME']))

        paths.append(os.path.join(self.root_path, 'themes', 'default'))
        paths.append(os.path.join(self.poobrain_path, 'themes', 'default'))

        return jinja2.FileSystemLoader(paths)


app = Poobrain(__name__) # TODO: Make app class configurable.

# delayed internal imports which may depend on app
import poobrains.helpers
import poobrains.rendering
import poobrains.form
import poobrains.storage
import poobrains.cli
import poobrains.auth


class ErrorPage(poobrains.rendering.Renderable):

    error = None
    code = None
    message = None

    def __init__(self, error):

        super(ErrorPage, self).__init__()

        self.error = error
        if hasattr(error, 'code'):
            self.code = error.code
        
        else:
            self.code = 'WTFBBQ'
            for cls, code in app.error_codes.iteritems():
                if isinstance(error, cls):
                    self.code = code
                    break

        self.title = "Ermahgerd, %d!" % self.code

        if isinstance(self.error, werkzeug.exceptions.HTTPException):
            self.message = error.description
        else:
            self.message = error.message


@poobrains.helpers.themed
def errorpage(error):

    if hasattr(error, 'code'):
        app.logger.error('Error %s when accessing %s: %s' % (error.code, flask.request.path, error.message))
        return (ErrorPage(error), error.code)

    app.logger.error('%s when accessing %s: %s' % (error.__class__.__name__, flask.request.path, error.message))
    return ErrorPage(error)

app.register_error_handler(400, errorpage)
app.register_error_handler(403, errorpage)
app.register_error_handler(404, errorpage)
app.register_error_handler(peewee.OperationalError, errorpage)
app.register_error_handler(peewee.IntegrityError, errorpage)
app.register_error_handler(peewee.DoesNotExist, errorpage)
