# -*- coding: utf-8 -*-

import math
import os
import collections

from poobrains import Response, app, abort, flash, g
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
        self.style = app.scss_compiler.compile_string("@import 'svg';")
    
    
    def templates(self, mode=None):

        r = super(SVG, self).templates(mode=mode)
        return ["svg/%s" % template for template in r]


    @poobrains.helpers.themed
    def view(self, mode=None, handle=None):

        if mode == 'raw':
            
            response = Response(self.render('raw'))
            response.headers['Content-Type'] = u'image/svg+xml'
            response.headers['Content-Disposition'] = u'filename="%s"' % 'map.svg'
            
            # Disable "public" mode caching downstream (nginx, varnish) in order to hopefully not leak restricted content
            response.cache_control.public = False
            response.cache_control.private = True
            response.cache_control.max_age = app.config['CACHE_LONG']

            return response
        
        else:
            return poobrains.helpers.ThemedPassthrough(super(SVG, self).view(mode=mode, handle=handle))


class DatasetForm(poobrains.auth.AddForm):

    def __init__(self, model_or_instance, **kwargs):

        super(DatasetForm, self).__init__(model_or_instance, **kwargs)

        n = 0
        for datapoint in self.instance.datapoints:
            
            name = 'datapoint-%d' % n
            setattr(self, name, DatapointFieldset(datapoint))
            n += 1

        setattr(self, 'datapoint-add', DatapointFieldset(Datapoint()))


class Dataset(poobrains.commenting.Commentable):

    form_edit = DatasetForm

    title = poobrains.storage.fields.CharField()
    description = poobrains.md.MarkdownField(null=True)
    label_x = poobrains.storage.fields.CharField(verbose_name="Label for the x-axis")
    label_y = poobrains.storage.fields.CharField(verbose_name="Label for the y-axis")


    @property
    def ref_id(self):
        return "dataset-%s" % self.name


    @property
    def authorized_datapoints(self):
        return Datapoint.list('read', g.user).where(Datapoint.dataset == self)


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

    dataset = poobrains.storage.fields.ForeignKeyField(Dataset, related_name='datapoints')
    x = poobrains.storage.fields.DoubleField()
    y = poobrains.storage.fields.DoubleField()
    error_lower = poobrains.storage.fields.FloatField(help_text="Lower margin of error", default=0.0)
    error_upper = poobrains.storage.fields.FloatField(help_text="Upper margin of error", default=0.0)

    @property
    def ref_id(self):
        return "dataset-%s-%s" % (self.dataset.name, self.x)


@app.expose('/svg/plot')
class Plot(SVG):

    width = None
    height = None
    padding = None
    inner_width = None
    inner_height = None

    datasets = None
    min_x = None
    max_x = None
    min_y = None
    max_y = None

    def __init__(self, handle=None, mode=None, **kwargs):

        super(Plot, self).__init__(handle=handle, mode=mode, **kwargs)

        if handle is None:
            abort(404)
        
        self.width = app.config['SVG_PLOT_WIDTH']
        self.height = app.config['SVG_PLOT_HEIGHT']
        self.padding = app.config['SVG_PLOT_PADDING']
        self.inner_width = self.width - (2 * self.padding)
        self.inner_height = self.height - (2 * self.padding)

        self.datasets = []
        dataset_names = handle.split(',')

        for name in dataset_names:

            try:
                ds = Dataset.load(name)
                if ds.permissions['read'].check(g.user):
                    self.datasets.append(ds)
            except (Dataset.DoesNotExist, poobrains.auth.AccessDenied):
                flash("Ignoring unknown MapDataset '%s'!" % name, 'error')

        all_x = []
        all_y = []

        for datapoint in Datapoint.list('read', g.user).where(Datapoint.dataset << self.datasets):
            all_x.append(datapoint.x)
            all_y.append(datapoint.y)

        if len(all_x):
            self.min_x = min(all_x)
            self.max_x = max(all_x)
            self.min_y = min(all_y)
            self.max_y = max(all_y)


    def normalize_x(self, value):

        span = self.max_x - self.min_x
        if span == 0.0:
            return self.inner_width / 2.0

        return (value - self.min_x) * (self.inner_width / span)


    def normalize_y(self, value):

        span = self.max_y - self.min_y
        if span == 0.0:
            return self.inner_height / 2.0

        return self.inner_height - (value - self.min_y) * (self.inner_height / span)


    @property
    def label_x(self):

        return u' / '.join([dataset.label_x for dataset in self.datasets])


    @property
    def label_y(self):

        return u' / '.join([dataset.label_y for dataset in self.datasets])


class MapDatasetForm(poobrains.auth.AddForm):

    def __init__(self, model_or_instance, **kwargs):

        super(MapDatasetForm, self).__init__(model_or_instance, **kwargs)

        n = 0
        for datapoint in self.instance.datapoints:
            
            name = 'datapoint-%d' % n
            setattr(self, name, MapDatapointFieldset(datapoint))
            n += 1

        setattr(self, 'datapoint-add', MapDatapointFieldset(MapDatapoint()))


class MapDataset(poobrains.commenting.Commentable):

    form_add = MapDatasetForm

    title = poobrains.storage.fields.CharField()
    description = poobrains.md.MarkdownField(null=True)


    @property
    def authorized_datapoints(self):
        return MapDatapoint.list('read', g.user).where(MapDatapoint.dataset == self)


class MapDatapointFieldset(poobrains.form.Fieldset):

    def __init__(self, datapoint, **kwargs):

        super(MapDatapointFieldset, self).__init__(**kwargs)

        self.datapoint = datapoint
        self.name = poobrains.form.fields.Text(type=poobrains.form.types.STRING, value=datapoint.name, placeholder=MapDatapoint.name.verbose_name, help_text=MapDatapoint.name.help_text)
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


class MapDatapoint(poobrains.tagging.Taggable):

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

            normalization_factor = 19994838.114 # this is the value this function would return for 85.0511° without normalization, which should™ make the map square
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
            #return 50 - 50 * (y / normalization_factor)
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

    def __init__(self, handle=None, mode=None, **kwargs):
        
        super(Map, self).__init__(handle=handle, mode=mode, **kwargs)
        
        if handle is None:
            abort(404)

        self.width = app.config['SVG_MAP_WIDTH']
        self.height = app.config['SVG_MAP_HEIGHT']

        self.datasets = []
        dataset_names = handle.split(',')

        for name in dataset_names:

            try:
                ds = MapDataset.load(name)
                if ds.permissions['read'].check(g.user):
                    self.datasets.append(ds)
            except (MapDataset.DoesNotExist, poobrains.auth.AccessDenied):
                flash("Ignoring unknown MapDataset '%s'!" % name, 'error')


for cls in set([SVG]).union(SVG.class_children()):
    rule = os.path.join("/svg/", cls.__name__.lower(), '<handle>', 'raw')
    app.site.add_view(cls, rule, mode='raw')
