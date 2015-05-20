from os.path import join, exists, dirname
from flask import abort, render_template


def view(f):

    def decorator(*args, **kwargs):

        # TODO: see if this can be obsoleted with abort and Flask.error_handler[_spec]
        try:
            content = f(*args, **kwargs)
        except Exception as e:
            print e
            abort(500, "VERY ERROR. SUCH DISGRACE. MANY SORRY.")

        return render_template('main.jinja', content=content)

    return decorator



class Renderable(object):

    def render(self, mode='full'):

        tpl_base = self.__class__.__name__.lower()

        tpls = [
            '%s-%s.jinja' % (tpl_base, mode),
            '%s.jinja' % (tpl_base,)
        ]

        return render_template(tpls, content=self)


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

    
    def append(self, path, caption):
        self.items.append((path, caption))
