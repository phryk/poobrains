from os.path import join, exists, dirname
from functools import wraps
from flask import abort, render_template, g
from werkzeug.wrappers import Response
from werkzeug.exceptions import HTTPException

import jinja2

# local imports 
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
                status_code = 200

            if isinstance(content, Response):
                return rv # pass Responses (i.e. redirects) upwards

            # This logic is redundant to Storable.render(mode).
            # It is "needed" in order for title to be set correctly
            # TODO: Don't Repeat Yourself.
            if mode in ('add', 'edit', 'delete'):
                if mode == 'add':
                    content = content.__class__.form()

                else:
                    content = content.form(mode=mode)


            g.title = content.title
            g.content = content

            return render_template('main.jinja', content=content, mode=mode), status_code

        return real

    return decorator


class Renderable(helpers.ChildAware):

    name = None
    title = None

    def __init__(self):

        self.name = self.__class__.__name__.lower()
        self.title = self.__class__.__name__

    
    def render(self, mode='full'): 

        tpls = self.template_candidates(mode)
        return jinja2.Markup(render_template(tpls, content=self, mode=mode))


    def template_candidates(self, mode):

        clsname = self.__class__.__name__.lower()

        tpls = [
            '%s-%s.jinja' % (clsname, mode),
            '%s.jinja' % (clsname,)
        ]

        for ancestor in self.__class__.ancestors(Renderable):

            clsname = ancestor.__name__.lower()

            tpls += [
                '%s-%s.jinja' % (clsname, mode),
                '%s.jinja' % (clsname,)
            ]

        return tpls


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

        self.url = url
        self.caption = caption
        self.active = active



class Menu(Renderable):

    name = None
    items = None

    def __init__(self, name):

        super(Menu, self).__init__()

        self.name = name
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
