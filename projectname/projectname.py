from flask import Flask, Blueprint
from playhouse.db_url import connect

from .db import BaseModel, db_proxy
import config


def install():

    print "db thingie: ", db_proxy.database, dir(db_proxy.database)
    db_proxy.create_tables()
    return "oink"


def db_connect():
    db_proxy.connect()


def db_close(dunnolol):
    if not db_proxy.is_closed():
        db_proxy.close()


class ProjectName(Flask):

    db = None
    config_whitelist = ['DATABASE', 'DEBUG', 'SECRET', 'MAY_INSTALL']


    def __init__(self, *args, **kwargs):

        super(ProjectName, self).__init__(*args, **kwargs)

        for option in self.config_whitelist:
            if hasattr(config, option):
                self.config[option] = getattr(config, option)

        if not self.config.has_key('MAY_INSTALL'):
            self.config['MAY_INSTALL'] = False

        if not self.config.has_key('THEME'):
            self.config['THEME'] = 'default'

        self.template_folder = 'themes/%s' % (self.config['THEME'],)

        self.db = connect(self.config['DATABASE'])
        db_proxy.initialize(self.db)

        if self.config['MAY_INSTALL']:
            self.add_url_rule('/install', 'install', install)


        # Make sure that each request has a proper database connection
        self.before_request(db_connect)
        self.teardown_request(db_close)
