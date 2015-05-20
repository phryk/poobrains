from flask import Flask
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
    menus = None


    def __init__(self, *args, **kwargs):

        super(ProjectName, self).__init__(*args, **kwargs)

        self.menus = {}

        for option in self.config_whitelist:
            if hasattr(config, option):
                self.config[option] = getattr(config, option)

        if not self.config.has_key('MAY_INSTALL'):
            self.config['MAY_INSTALL'] = False

        self.template_folder = 'themes/%s' % (self.config['THEME'],)

        self.db = connect(self.config['DATABASE'])
        db_proxy.initialize(self.db)

        if self.config['MAY_INSTALL']:
            self.add_url_rule('/install', 'install', install)


        # Make sure that each request has a proper database connection
        self.before_request(request_setup)
        self.teardown_request(request_teardown)


    def add_menu(self, menu):
        self.menus[menu.name] = menu
