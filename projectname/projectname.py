from flask import Flask, Blueprint
from playhouse.db_url import connect as db_connect

from .db import db_proxy
import config


class ProjectName(Flask):

    db = None
    config_whitelist = ['DATABASE', 'DEBUG', 'SECRET']


    def __init__(self, *args, **kwargs):

        super(ProjectName, self).__init__(*args, **kwargs)

        for option in self.config_whitelist:
            if hasattr(config, option):
                self.config[option] = getattr(config, option)

        if not self.config.has_key('THEME'):
            self.config['THEME'] = 'default'

        self.template_folder = 'themes/%s' % (self.config['THEME'],)
        print "dem current template folder: ", self.template_folder

        self.db = db_connect(self.config['DATABASE'])
        db_proxy.initialize(self.db)
