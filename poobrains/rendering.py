from os.path import join, exists, dirname
from functools import wraps
from flask import abort, render_template, g
from werkzeug.wrappers import Response
from werkzeug.exceptions import HTTPException

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


            if hasattr(content, 'title') and content.title:
                g.title = content.title

            elif hasattr(content, 'name') and content.name:
                g.title = content.name.capitalize()

            else:
                g.title = content.__class__.__name__
            g.content = content

            if hasattr(g, 'user'):
                user = g.user
            else:
                user = None
            return render_template('main.jinja', content=content, mode=mode, user=user), status_code

        return real

    return decorator


class Renderable(helpers.ChildAware):

    name = None

    def __init__(self):

        self.name = self.__class__.__name__.lower()

    
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

        poobrains.app.logger.debug("template_candidates")
        poobrains.app.logger.debug(tpls)

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
    title = None
    items = None

    def __init__(self, name, title=None):

        super(Menu, self).__init__()

        self.name = name
        self.title = title if title else name.capitalize()
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
