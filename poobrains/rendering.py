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


    def __init__(self, name=None, **kwargs):

        self.name = name
        self.url = self.instance_url # make .url callable for class and instances


    @classmethod
    def url(cls, mode='teaser'):
        return poobrains.app.get_url(cls, mode=mode)


    def instance_url(self, mode='full'):
        
        url_params = {}
        if getattr(self, 'handle', False):
            url_params['handle'] = self.handle
        return poobrains.app.get_url(self.__class__, mode=mode, **url_params)


    def templates(self, mode=None):

        tpls = []

        for x in [self.__class__] + self.__class__.ancestors():

            name = x.__name__.lower()
                
            if mode:
                tpls.append('%s-%s.jinja' % (name, mode))

            tpls.append('%s.jinja' % name)

        return tpls


    @classmethod
    def class_view(cls, **kwargs):
        
        """
        view function to be called in a flask request context
        """

        instance = cls(**kwargs)
        return instance.view(**kwargs)


    @poobrains.helpers.themed
    def view(self, mode='full', **kwargs):

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


class Container(Renderable):

    title = None
    items = None
    menu_actions = None

    def __init__(self, title=None, items=None, menu_actions=None, **kwargs):

        super(Container, self).__init__(**kwargs)

        self.title = title
        if self.title is None:
            self.title = self.__class__.__name__

        self.items = items
        if self.items is None:
            self.items = []

        self.menu_actions = menu_actions


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


    def append(self, item):
        self.items.append(item)

    def clear(self):
        self.items.clear()

    
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


class Menu(Container):

    name = None
    title = None
    items = None

    def __init__(self, name, title=None):

        super(Menu, self).__init__(name=name)

        if title:
            self.title = title

        self.items = []


    def append(self, url, caption, active=None):
        self.items.append(MenuItem(url, caption, active))


class RowIterator(object):

    row = None
    current_idx = None

    def __init__(self, row):
        self.row = row
        self.current_idx = -1 # so first next call uses 0


    def __iter__(self):
        return self


    def next(self):
        self.current_idx += 1

        if self.current_idx >= len(self.row.columns):
            raise StopIteration()

        return self.row._data[self.current_idx]


class TableRow(object):

    columns = None
    _data = None

    def __init__(self, columns = [], *data, **kwdata):

        self.columns = columns
        self._data = []

        for i in range(0, len(columns)):
            self[i] = None

        for i in range(0, len(data)):
            self[i] = data[i]

        for key, value in kwdata.iteritems():
            self[key] = value


    def __getitem__(self, key):

        idx = self._get_idx(key)
        return self._data[idx]


    def __setitem__(self, key, value):

        idx = self._get_idx(key)
        self._data[idx] = value


    def __delitem__(self, key):

        idx = self._get_idx(key)
        self._data[idx] = None


    def __iter__(self):
        return RowIterator(self)


    def _get_idx(self, key):

        if not isinstance(key, int):
            return key

        columns_lower = [column.lower for column in self.columns]
        if key.lower() in columns_lower:
            return columns_lower.index(key.lower())

        raise KeyError("Column %s is unknown!" % key)


class Table(Renderable):

    rows = None
    columns = None

    def __init__(self, columns = [], rows = [], **kwargs):

        super(Table, self).__init__(**kwargs)
        self.columns = []
        self.rows = rows


    def append(self, *data, **kwdata):
        self.rows.append(TableRow(columns=self.columns))
