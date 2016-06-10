from os.path import join, exists, dirname
from functools import wraps
from flask import abort, render_template, g
from werkzeug.wrappers import Response
from werkzeug.exceptions import HTTPException

import flask
import werkzeug
import jinja2

# local imports 
import poobrains
import helpers

def render(mode='full'):

    def decorator(f):

        @wraps(f)
        def real(*args, **kwargs):

            rv = f(*args, **kwargs)

            if isinstance(rv, tuple):
                content = rv[0]
                status_code = rv[1]

            else:
                content = rv
                status_code = 200 # TODO: Find out if this is too naive

            if isinstance(content, Response):
                return rv # pass Responses (i.e. redirects) upwards

            if hasattr(content, 'title') and content.title:
                print "RENDER HAS TITLE"
                g.title = "YOINK"
                #g.title = content.title

            elif hasattr(content, 'name') and content.name:
                print "RENDER HAS NO TITLE"
                print content
                if hasattr(content, 'title'):
                    print type(content.title), content.title
                g.title = "BOINK"
                #g.title = content.name

            else:
                g.title = content.__class__.__name__
            g.content = content

            if hasattr(g, 'user'):
                user = g.user
            else:
                user = None
            return flask.render_template('main.jinja', content=content, mode=mode, user=user), status_code

        return real

    return decorator


class Renderable(helpers.ChildAware):

    name = None

    def __init__(self):

        self.name = self.__class__.__name__.lower()
        self.templates = self.instance_templates

    
    @classmethod
    def templates(cls, mode=None):

        tpls = []

        for x in [cls] + cls.ancestors():

            name = x.__name__.lower()
                
            if mode:
                tpls.append('%s-%s.jinja' % (name, mode))

            tpls.append('%s.jinja' % name)

        return tpls


    def instance_templates(self, mode=None):
        return self.__class__.templates(mode)

    
    def render(self, mode=None):

        tpls = self.templates(mode)
        return jinja2.Markup(flask.render_template(tpls, content=self, mode=mode))


class RenderString(Renderable):

    value = None

    def __init__(self, value):
        self.value = value


    def render(self, mode=None):
        return self.value


class MenuItem(object):

    url = None
    caption = None
    active = None

    def __init__(self, url, caption, active=False):

        super(MenuItem, self).__init__()
        self.url = url
        self.caption = caption
        self.active = active



class Menu(Renderable):

    name = None
    title = None
    items = None

    def __init__(self, name, title=None):

        super(Menu, self).__init__()

        self.name = name
        self.title = title if title else name
        self.items = []


    def __len__(self):
        return self.items.__len__()


    def __getitem__(self, key):
        return self.items.__getitem__(key)


    def __setitem__(self, key, value):
        return self.items.__setitem__(key, value)


    def __delitem__(self, key):
        return self.items.__delitem__(key)


    def __iter__(self):
        return self.items.__iter__()

    
    def append(self, url, caption, active=False):
        self.items.append(MenuItem(url, caption, active))
