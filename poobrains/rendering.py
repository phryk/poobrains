import collections
import os
import flask
import werkzeug
import jinja2

# local imports 
import poobrains
import helpers


class Renderable(helpers.ChildAware):

    name = None


    class Meta:
        ops = collections.OrderedDict([('r', 'read')])
        modes = collections.OrderedDict([('full', 'r')])


    def __init__(self, name=None):

        self.name = name
        self.url = self.instance_url # make .url callable for class and instances


    @classmethod
    def url(cls, mode=None):
        return poobrains.app.get_url(cls, mode=mode)


    def instance_url(self, mode=None):
        return poobrains.app.get_url(self.__class__, handle=getattr(self, 'handle', None), mode=mode) # FIXME/TODO: at least the naming doesn't fit. Ponder instantiated Renderables which are not Storables.


    def templates(self, mode=None):

        tpls = []

        for x in [self.__class__] + self.__class__.ancestors():

            name = x.__name__.lower()
                
            if mode:
                tpls.append('%s-%s.jinja' % (name, mode))

            tpls.append('%s.jinja' % name)

        return tpls


    @classmethod
    def class_view(cls, mode='full', *args, **kwargs):
        
        """
        view function to be called in a flask request context
        """

        instance = cls(*args, **kwargs)
        return instance.view(mode, *args, **kwargs)


    @poobrains.helpers.themed
    def view(self, mode='full', *args, **kwargs):

        """
        view function to be called in a flask request context
        """

        return self


    def render(self, mode='full'):
        
        tpls = self.templates(mode)
        return jinja2.Markup(flask.render_template(tpls, content=self, mode=mode))


    
class RenderString(Renderable):

    value = None

    def __init__(self, value, name=None):
        super(RenderString, self).__init__(name=name)
        self.value = value


    def render(self, mode='full'):
        return self.value # TODO: cast to jinja2.Markup or sth?


class MenuItem(object):

    url = None
    caption = None
    active = None

    def __init__(self, url, caption, active=None):

        super(MenuItem, self).__init__()
        self.url = url
        self.caption = caption
        if active is not None:
            self.active = 'active' if active is True else active
        else:
            if self.url == flask.request.path:
                self.active = 'active'
            elif flask.request.path.startswith(os.path.join(self.url, '')):
                self.active = 'trace'


class Menu(Renderable):

    name = None
    title = None
    items = None

    def __init__(self, name, title=None):

        super(Menu, self).__init__(name=name)

        if title:
            self.title = title

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

    
    def append(self, url, caption, active=None):
        self.items.append(MenuItem(url, caption, active))
