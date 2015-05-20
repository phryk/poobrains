from os.path import join, exists
from flask import abort, render_template
import config


def view(f):

    def wrap(*args, **kwargs):

        try:
            content = f(*args, **kwargs)
        except Exception as e:
            abort(500, "VERY ERROR. SUCH DISGRACE. MANY SORRY.")


        tpls = []
        if config.THEME != 'default':
            tpls.append(join(config.THEME, 'main.jinja'))
        tpls.append('default/main.jinja')

        return render_template(tpls, content=content)

    return wrap



class Renderable(object):

    theme = None

    def __init__(self, theme=None):

        if theme is not None:
            self.theme = theme
        else:
            self.theme = config.THEME


    def render(mode='full'):

        tpl_default = self.__class__
        tpl_mode = '%s-%s' % (self.__class__, mode)

        tpls = []
        
        if self.theme is not 'default':
            tpls.append(join(self.theme, tpl_mode))
            tpl.append(join(self.theme, tpl_default))
        
        tpls.append(join('default', tpl_mode))
        tpls.append(join('default', tpl_default))


        return render_template(tpls, {'obj': self})


class Menu(Renderable):

    name = None
    items = None

    def __init__(self, name, theme=None):

        super(Menu, self).__init__(theme=theme)

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

    
    def append(self, path, caption):
        self.items.append((path, caption))
