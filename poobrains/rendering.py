from os.path import join, exists, dirname
from functools import wraps
from flask import abort, render_template, current_app, g
from werkzeug.exceptions import HTTPException


def render(f):

    @wraps(f)
    def decorator(*args, **kwargs):

        try:
            rv = f(*args, **kwargs)

            if isinstance(rv, tuple):
                content = rv[0]
                status_code = rv[1]

            else:
                content = rv
                status_code = 200

            g.title = content.title
            g.content = content # TODO: Is this used? Is this needed?

            return render_template('main.jinja', content=content), status_code

        except Exception as e:
            if isinstance(e, HTTPException) or current_app.debug:
                raise # let exceptions raised by abort() pass up

            abort(500, "Somebody set up us the bomb. @render error.")

    return decorator



class ChildAware(object):

    @classmethod
    def children(cls):

        children = cls.__subclasses__()

        for child in children:
            children += child.children()

        return children


    @classmethod
    def ancestors(cls, top=None):

        """
        params:
            * top: class, when this class is reached, the iteration is stopped
        """

        if top is None:
            top = ChildAware

        whitelist = [top] + top.children()
        ancestors = []

        for base in cls.__bases__:

            if base in whitelist:
                ancestors.append(base)

                if base is top:
                    break

                ancestors += base.ancestors(top)

        return ancestors



class Renderable(ChildAware):

    name = None
    title = None

    def __init__(self):

        self.name = self.__class__.__name__.lower()
        self.title = self.__class__.__name__

    
    def render(self, mode='full'): 

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

        return render_template(tpls, content=self, mode=mode)


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
