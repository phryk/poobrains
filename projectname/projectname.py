from os.path import join, dirname
from flask import Flask, g
from flask.helpers import locked_cached_property
from jinja2 import FileSystemLoader
from playhouse.db_url import connect

from .db import BaseModel, db_proxy
import config


def install():

    db_proxy.create_tables(BaseModel.children())
    return "Installation procedure complete."


def request_setup():
    db_proxy.connect()


def request_teardown(dunnolol):
    if not db_proxy.is_closed():
        db_proxy.close()


class ProjectName(Flask):

    db = None
    config_whitelist = ['DATABASE', 'DEBUG', 'SECRET', 'MAY_INSTALL', 'THEME']
    boxes = None


    def __init__(self, *args, **kwargs):

        super(ProjectName, self).__init__(*args, **kwargs)

        self.boxes = {}

        for option in self.config_whitelist:
            if hasattr(config, option):
                self.config[option] = getattr(config, option)

        if not self.config.has_key('MAY_INSTALL'):
            self.config['MAY_INSTALL'] = False

        if not self.config.has_key('THEME'):
            self.config['THEME'] = 'default'

        self.db = connect(self.config['DATABASE'])
        db_proxy.initialize(self.db)

        if self.config['MAY_INSTALL']:
            self.add_url_rule('/install', 'install', install)


        # Make sure that each request has a proper database connection
        self.before_request(request_setup)
        self.teardown_request(request_teardown)

        self.before_request(self.build_boxes)

    def build_boxes(self):

        g.boxes = {}
        print "build_boxes function called.", self
        for name, f in self.boxes.iteritems():
            print "dem f: ", f, f()
            g.boxes[name] = f()
    
    
    @locked_cached_property
    def jinja_loader(self):

        paths = []

        if self.config['THEME'] != 'default':
            print "THEME: ", self.config['THEME']
            paths.append(join(self.root_path, 'themes', self.config['THEME']))
            paths.append(join(dirname(__file__), 'themes', self.config['THEME']))

        paths.append(join(self.root_path, 'themes', 'default'))
        paths.append(join(dirname(__file__), 'themes', 'default'))

        return FileSystemLoader(paths)


    def box(self, name):

        def decorator(f):
            self.boxes[name] = f
            return f

        return decorator
