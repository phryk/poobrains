from os.path import join, exists, dirname
from functools import wraps
from flask import abort, render_template, current_app, g



def render(f):

    @wraps(f)
    def decorator(*args, **kwargs):

        content = f(*args, **kwargs)
        g.title = content.title
        g.content = content
        return render_template('main.jinja', content=content)

    return decorator



class ChildAware(object):

    @classmethod
    def children(cls):

        children = cls.__subclasses__()

        if len(children):
            for child in children:
                grandchildren = child.children()

            for grandchild in grandchildren:
                children.append(grandchild)

        return children



class Renderable(ChildAware):

    name = None
    title = None

    def __init__(self):

        self.name = self.__class__.__name__.lower()
        self.title = self.__class__.__name__

    
    def render(self, mode='full'):

        tpl_base = self.__class__.__name__.lower()

        tpls = [
            '%s-%s.jinja' % (tpl_base, mode),
            '%s.jinja' % (tpl_base,)
        ]

        return render_template(tpls, content=self)


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
