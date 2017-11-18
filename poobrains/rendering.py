# -*- coding: utf-8 -*-

import collections
import os
import flask
import werkzeug
import jinja2

# local imports 
#import poobrains
from poobrains import app
import poobrains.helpers
#import poobrains.form


class Renderable(poobrains.helpers.ChildAware):

    name = None
    css_class = None


    class Meta:
        modes = collections.OrderedDict([('full', 'read')])


    def __init__(self, name=None, css_class=None, **kwargs):

        self.name = name
        self.url = self.instance_url # make .url callable for class and instances

        self.css_class = css_class
        if self.css_class is None:
            self.css_class = ''


    @property
    def title(self):

        if self.name:
            return self.name

        return self.__class__.__name__


    @classmethod
    def url(cls, mode='teaser', quiet=False, **url_params):

        if quiet:
            try:
                return app.get_url(cls, mode=mode, **url_params)
            except:
                return False

        return app.get_url(cls, mode=mode, **url_params)


    def instance_url(self, mode='full', quiet=False, **url_params):
 
        if getattr(self, 'handle', False): 
            url_params['handle'] = self.handle

        if quiet:
            try:
                return app.get_url(self.__class__, mode=mode, **url_params)
            except:
                return False

        return app.get_url(self.__class__, mode=mode, **url_params)


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


    #def render(self, mode='full'):
    #    return self.value # TODO: cast to jinja2.Markup or sth?


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
            check_request = werkzeug.urls.url_fix(flask.request.path)
            check_self = werkzeug.urls.url_fix(self.url)

            if check_self == check_request:
                self.active = 'active'
            elif check_request.startswith(os.path.join(check_self, '')):
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


class Tree(Renderable):

    root = None
    children = None
    mode = None

    def __init__(self, root, name=None, mode=None, **kwargs):
        
        super(Tree, self).__init__(name=name, **kwargs)
        self.root = root if root is not None else RenderString('tree root')
        self.children = []
        self.mode = mode if mode is not None else 'teaser'


class TableRow(object):

    classes = None
    _columns = None # don't set this manually, but only indirectly via Table.columns
    _data = None

    def __init__(self, columns, *data, **kwdata):

        super(TableRow, self).__setattr__('_columns', columns)

        if kwdata.has_key('_classes'):
            self.classes = kwdata.pop('_classes')

        self._data = []

        for i in range(0, len(columns)):
            self.append(None)

        for i in range(0, len(data)):
            self[i] = data[i]

        for key, value in kwdata.iteritems():
            self[key] = value


    def __getitem__(self, key):

        idx = self._get_idx(key)
        return self._data[idx]


    def __setitem__(self, key, value):

        idx = self._get_idx(key)

        if len(self._data) > idx:
            self._data[idx] = value
        else:
            self._data.insert(idx, value)


    def __delitem__(self, key):

        idx = self._get_idx(key)
        self._data[idx] = None


    def __iter__(self):
        return RowIterator(self)


    def __setattr__(self, name, value):

        if name == '_columns':
            
            new_data = []
            for column in value:
                try:
                    new_data.append(self[column])
                except IndexError:
                    new_data.append(None)

            self._data = new_data

        super(TableRow, self).__setattr__(name, value)


    def _get_idx(self, key):

        if isinstance(key, int):
            return key

        columns_lower = [column.lower for column in self._columns]
        if key.lower() in columns_lower:
            return columns_lower.index(key.lower())

        raise KeyError("Column %s is unknown!" % key)


    def append(self, value):

        self._data.append(value)


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

        if self.current_idx >= len(self.row._data):
            raise StopIteration()

        return self.row._data[self.current_idx]


class MagicColumns(list):

    table = None

    def __init__(self, table, iterable=[]):

        super(MagicColumns, self).__init__(iterable)
        self.table = table

    def __setitem__(self, idx, value):

        super(MagicColumns, self).__setitem__(idx, value)
        self.table._columns_updated()
    
    
    def __delitem__(self, idx):

        super(MagicColumns, self).__delitem__(idx)
        self.table._columns_updated()


    def append(self, item):

        super(MagicColumns, self).append(item)
        self.table._columns_updated()


class Table(Renderable):

    rows = None
    columns = None

    def __init__(self, columns = None, rows = None, **kwargs):
        
        super(Table, self).__init__(**kwargs)

        if columns is None:
            self.columns = []
        else:
            self.columns = columns

        if rows is None:
            self.rows = []
        else:
            self.rows = rows

    
    def __setattr__(self, name, value):

        if name == 'columns':
            value = MagicColumns(self, value)

        super(Table, self).__setattr__(name, value)


    def _columns_updated(self):

        if len(self.columns):
            for row in self.rows:
                row._columns = list(self.columns)


    def append(self, *data, **kwdata):
        self.rows.append(TableRow(list(self.columns), *data, **kwdata))
