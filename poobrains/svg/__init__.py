# -*- coding: utf-8 -*-

import math
import os
import collections
import json

from poobrains import Response, Markup, app, abort, flash, g
import poobrains.helpers
import poobrains.storage
import poobrains.auth
import poobrains.tagging
import poobrains.commenting

class SVG(poobrains.auth.Protected):
    
    handle = None # needed so that app.expose registers a route with extra param, this is kinda hacky…
    
    class Meta:

        modes = collections.OrderedDict([
            ('teaser', 'read'),
            ('full', 'read'),
            ('raw', 'read'),
            ('inline', 'read')
        ])
    
    style = None

    def __init__(self, handle=None, mode=None, **kwargs):

        super(SVG, self).__init__(**kwargs)

        self.handle = handle
        self.style = Markup(app.scss_compiler.compile_string("@import 'svg';"))
    
    
    def templates(self, mode=None):

        r = super(SVG, self).templates(mode=mode)
        return ["svg/%s" % template for template in r]


    @poobrains.helpers.themed
    def view(self, mode=None, handle=None):

        if mode == 'raw':
            
            response = Response(self.render('raw'))
            response.headers['Content-Type'] = u'image/svg+xml'
            response.headers['Content-Disposition'] = u'filename="%s.svg"' % self.__class__.__name__
            
            # Disable "public" mode caching downstream (nginx, varnish) in order to hopefully not leak restricted content
            response.cache_control.public = False
            response.cache_control.private = True
            response.cache_control.max_age = app.config['CACHE_LONG']

            return response
        
        else:
            return poobrains.helpers.ThemedPassthrough(super(SVG, self).view(mode=mode, handle=handle))


class Dataset(poobrains.commenting.Commentable):


    title = poobrains.storage.fields.CharField()
    description = poobrains.md.MarkdownField(null=True)
    label_x = poobrains.storage.fields.CharField(verbose_name="Label for the x-axis")
    label_y = poobrains.storage.fields.CharField(verbose_name="Label for the y-axis")
    #grid_step_x = poobrains.storage.fields.DoubleField(default=1.0)
    #grid_step_y = poobrains.storage.fields.DoubleField(default=1.0)

    @property
    def ref_id(self):
        return "dataset-%s" % self.name


    @property
    def authorized_datapoints(self):
        return Datapoint.list('read', g.user).where(Datapoint.dataset == self)

    
    def datapoint_id(self, datapoint):
        return "dataset-%s-%s" % (self.name, datapoint.x)

    
    def plot(self):

        return Plot(datasets=[self]).render('full')


class DatapointFieldset(poobrains.form.Fieldset):

    def __init__(self, datapoint, **kwargs):

        super(DatapointFieldset, self).__init__(**kwargs)

        self.datapoint = datapoint
        self.x = poobrains.form.fields.Text(type=poobrains.form.types.FLOAT, value=self.datapoint.x, placeholder=Datapoint.x.verbose_name, help_text=Datapoint.x.help_text)
        self.y = poobrains.form.fields.Text(type=poobrains.form.types.FLOAT, value=self.datapoint.y, placeholder=Datapoint.y.verbose_name, help_text=Datapoint.y.help_text)
        self.error_lower = poobrains.form.fields.Text(type=poobrains.form.types.FLOAT, value=self.datapoint.error_lower, placeholder=Datapoint.error_lower.verbose_name, help_text=Datapoint.error_lower.help_text)
        self.error_upper = poobrains.form.fields.Text(type=poobrains.form.types.FLOAT, value=self.datapoint.error_upper, placeholder=Datapoint.error_upper.verbose_name, help_text=Datapoint.error_upper.help_text)


    def process(self, submit, dataset):

        if self.datapoint in dataset.datapoints:
            pass # florp
        else:
            self.datapoint.dataset = dataset
            self.datapoint.x = self.fields['x'].value
            self.datapoint.y = self.fields['y'].value
            self.datapoint.error_lower = self.fields['error_lower'].value
            self.datapoint.error_upper = self.fields['error_upper'].value

            self.datapoint.save(force_insert=True)


class Datapoint(poobrains.auth.Owned):

    class Meta:
        order_by = ['dataset', 'x']
        primary_key = poobrains.storage.CompositeKey('dataset', 'x')
        related_use_form = True

    dataset = poobrains.storage.fields.ForeignKeyField(Dataset, related_name='datapoints')
    x = poobrains.storage.fields.DoubleField()
    y = poobrains.storage.fields.DoubleField()
    error_lower = poobrains.storage.fields.FloatField(help_text="Lower margin of error", default=0.0)
    error_upper = poobrains.storage.fields.FloatField(help_text="Upper margin of error", default=0.0)


@app.expose('/svg/plot')
class Plot(SVG):

    padding = None
    width = None
    height = None
    inner_width = None
    inner_height = None
    plot_width = None
    plot_height = None
    description_height = None

    datasets = None
    min_x = None
    max_x = None
    min_y = None
    max_y = None
    span_x = None
    span_y = None
        

    class Meta:

        modes = collections.OrderedDict([
            ('teaser', 'read'),
            ('full', 'read'),
            ('raw', 'read'),
            ('json', 'read'),
            ('inline', 'read')
        ])

    def __init__(self, handle=None, mode=None, datasets=None, **kwargs):

        super(Plot, self).__init__(handle=handle, mode=mode, **kwargs)

        if handle is None and datasets is None:
            abort(404, "No datasets selected")
        
        self.padding = app.config['SVG_PLOT_PADDING']
        self.plot_width = app.config['SVG_PLOT_WIDTH']
        self.plot_height = app.config['SVG_PLOT_HEIGHT']
        self.description_height = app.config['SVG_PLOT_DESCRIPTION_HEIGHT']
        self.width = self.plot_width + (2 * self.padding)
        self.height = self.plot_height + self.description_height + (3 * self.padding)
        self.inner_width = self.width - (2 * self.padding)
        self.inner_height = self.height - (2 * self.padding)

        if datasets:
            self.datasets = datasets

        else:

            self.datasets = []
            dataset_names = handle.split(',')

            for name in dataset_names:

                try:
                    ds = Dataset.load(name)
                    if ds.permissions['read'].check(g.user):
                        self.datasets.append(ds)
                except (Dataset.DoesNotExist, poobrains.auth.AccessDenied):
                    #flash("Ignoring unknown Dataset '%s'!" % name, 'error')
                    pass

        self.handle = ','.join([ds.name for ds in self.datasets]) # needed for proper URL generation

        datapoint_count = 0
        for datapoint in Datapoint.list('read', g.user).where(Datapoint.dataset << self.datasets):

            datapoint_count += 1

            y_lower = datapoint.y
            if datapoint.error_lower:
                y_lower -= datapoint.error_lower

            y_upper = datapoint.y
            if datapoint.error_upper:
                y_upper += datapoint.error_upper


            if self.min_x is None or datapoint.x < self.min_x:
                self.min_x = datapoint.x

            if self.max_x is None or datapoint.x > self.max_x:
                self.max_x = datapoint.x
               
            if self.min_y is None or y_lower < self.min_y:
                self.min_y = y_lower

            if self.max_y is None or y_upper > self.max_y:
                self.max_y = y_upper

        if datapoint_count > 0:
            self.span_x = self.max_x - self.min_x
            self.span_y = self.max_y - self.min_y

        else:
            self.min_x = 0
            self.max_x = 0
            self.min_y = 0
            self.max_y = 0
            self.span_x = 0
            self.span_y = 0


    def render(self, mode=None):

        if mode == 'json':

            data = {}

            for dataset in self.datasets:
                data[dataset.name] = []

                for datapoint in dataset.authorized_datapoints:
                    data[dataset.name].append({
                        'x': datapoint.x,
                        'y': datapoint.y,
                        'error_lower': datapoint.error_lower,
                        'error_upper': datapoint.error_upper
                    })

            return Markup(json.dumps(data))

        return super(Plot, self).render(mode=mode)


    def normalize_x(self, value):

        if self.span_x == 0.0:
            return self.plot_width / 2.0

        return (value - self.min_x) * (self.plot_width / self.span_x)


    def normalize_y(self, value):

        if self.span_y == 0.0:
            return self.plot_height / 2.0

        return self.plot_height - (value - self.min_y) * (self.plot_height / self.span_y)


    @property
    def label_x(self):

        return u' / '.join([dataset.label_x for dataset in self.datasets])


    @property
    def label_y(self):

        return u' / '.join([dataset.label_y for dataset in self.datasets])


    @property
    def grid_x(self):

        if self.span_x == 0:
            return [self.min_x]

        grid_step = 10 ** (int(math.log10(self.span_x)) - 1)

        offset = (self.min_x % grid_step) * grid_step # distance from start of plot to first line on the grid
        start = self.min_x + offset

        x = start
        coords = [x]
        while x <= self.max_x:
            coords.append(x)
            x += grid_step

        return coords


    @property
    def grid_y(self):

        if self.span_y == 0:
            return [self.min_y]

        grid_step = 10 ** (int(math.log10(self.span_y)) - 1)

        offset = (self.min_y % grid_step) * grid_step # distance from start of plot to first line on the grid
        start = self.min_y + offset

        y = start
        coords = [y]
        while y <= self.max_y:
            coords.append(y)
            y += grid_step

        return coords


class MapDataset(poobrains.commenting.Commentable):

    title = poobrains.storage.fields.CharField()
    description = poobrains.md.MarkdownField(null=True)


    @property
    def authorized_datapoints(self):
        return MapDatapoint.list('read', g.user).where(MapDatapoint.dataset == self)
    
    
    def plot(self):

        return Map(datasets=[self]).render('full')


class MapDatapointFieldset(poobrains.form.Fieldset):

    def __init__(self, datapoint, **kwargs):

        super(MapDatapointFieldset, self).__init__(**kwargs)

        self.datapoint = datapoint
        self.title = poobrains.form.fields.Text(type=poobrains.form.types.STRING, value=datapoint.title, placeholder=MapDatapoint.title.verbose_name, help_text=MapDatapoint.title.help_text)
        self.latitude = poobrains.form.fields.Text(type=poobrains.form.types.FLOAT, value=self.datapoint.x, placeholder=MapDatapoint.latitude.verbose_name, help_text=MapDatapoint.latitude.help_text)
        self.longitude = poobrains.form.fields.Text(type=poobrains.form.types.FLOAT, value=self.datapoint.y, placeholder=MapDatapoint.longitude.verbose_name, help_text=MapDatapoint.longitude.help_text)
        self.description = poobrains.form.fields.TextArea(placeholder=MapDatapoint.description.verbose_name, help_text=MapDatapoint.description.help_text)


    def process(self, submit, dataset):

        if self.datapoint in dataset.datapoints:
            pass # florp
        else:
            self.datapoint.dataset = dataset

            self.datapoint.name = self.fields['name'].value
            self.datapoint.latitude = self.fields['latitude'].value
            self.datapoint.longitude = self.fields['longitude'].value
            self.datapoint.description = self.fields['description'].value

            self.datapoint.save(force_insert=True)


class MapDatapoint(poobrains.auth.Owned):

    class Meta:
        related_use_form = True


    width = None
    height = None

    dataset = poobrains.storage.fields.ForeignKeyField(MapDataset, related_name='datapoints')
    title = poobrains.storage.fields.CharField()
    description = poobrains.md.MarkdownField(null=True)
    latitude = poobrains.storage.fields.DoubleField()
    longitude = poobrains.storage.fields.DoubleField()


    def __init__(self, *args, **kwargs):

        super(MapDatapoint, self).__init__(*args, **kwargs)
        self.width = app.config['SVG_MAP_WIDTH']
        self.height = app.config['SVG_MAP_HEIGHT']
        self.infobox_width = app.config['SVG_MAP_INFOBOX_WIDTH']
        self.infobox_height = app.config['SVG_MAP_INFOBOX_HEIGHT']


    @property
    def ref_id(self):
        return "dataset-%s-%s" % (self.dataset.name, self.id)

    # mercator calculation shamelessly thieved from the osm wiki
    # http://wiki.openstreetmap.org/wiki/Mercator
    # NOTE: I *think* this is WGS84?
    # NOTE: r_minor seems to have been WGS84 but missed a few decimal places

    @property
    def x(self):

        if not self.longitude is None:

            normalization_factor = 20037508.3428

            r_major=6378137.000
            x = r_major*math.radians(self.longitude)
            #return 50 + 50 * (x / normalization_factor)
            
            return (self.width  / 2.0) + (self.width / 2.0) * (x / normalization_factor)


    @property
    def y(self):

        if not self.latitude is None:

            #normalization_factor = 19994838.114 # this is the value this function would return for 85.0511° without normalization, which should™ make the map square
            normalization_factor = 12890914.1373 # this is the value this function would return for 75° without normalization, which should™ make the map square
            if self.latitude>89.5:self.latitude=89.5
            if self.latitude<-89.5:self.latitude=-89.5
            r_major=6378137.000
            r_minor=6356752.3142518
            temp=r_minor/r_major
            eccent=math.sqrt(1-temp**2)
            phi=math.radians(self.latitude)
            sinphi=math.sin(phi)
            con=eccent*sinphi
            com=eccent/2
            con=((1.0-con)/(1.0+con))**com
            ts=math.tan((math.pi/2-phi)/2)/con
            y=0-r_major*math.log(ts)

            return (self.height / 2.0) - (self.height / 2.0) * (y / normalization_factor)


    @property
    def infobox_x(self):
        max_x = self.width - self.infobox_width - 10
        return self.x if self.x < max_x else max_x


    @property
    def infobox_y(self):
        max_y = self.height - self.infobox_height - 10
        return self.y if self.y < max_y else max_y


@app.expose('/svg/map')
class Map(SVG):
    
    width = None
    height = None

    datasets = None

    def __init__(self, handle=None, mode=None, datasets=None, **kwargs):
        
        super(Map, self).__init__(handle=handle, mode=mode, **kwargs)
        
        if handle is None and datasets is None:
            abort(404, "No datasets selected")

        self.width = app.config['SVG_MAP_WIDTH']
        self.height = app.config['SVG_MAP_HEIGHT']

        if datasets:
            self.datasets = datasets

        else:

            self.datasets = []
            dataset_names = handle.split(',')

            for name in dataset_names:

                try:
                    ds = MapDataset.load(name)
                    if ds.permissions['read'].check(g.user):
                        self.datasets.append(ds)
                except (MapDataset.DoesNotExist, poobrains.auth.AccessDenied):
                    #flash("Ignoring unknown MapDataset '%s'!" % name, 'error')
                    pass

        self.handle = ','.join([ds.name for ds in self.datasets]) # needed for proper URL generation


for cls in set([SVG]).union(SVG.class_children()):
    rule = os.path.join("/svg/", cls.__name__.lower(), '<handle>', 'raw')
    app.site.add_view(cls, rule, mode='raw')
