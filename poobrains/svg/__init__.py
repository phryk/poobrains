# -*- coding: utf-8 -*-

import math
import os
import collections

from poobrains import Response, app, abort
import poobrains.helpers
import poobrains.rendering
import poobrains.storage
import poobrains.tagging
import poobrains.commenting

class SVG(poobrains.rendering.Renderable):
    
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


    @poobrains.helpers.themed
    def view(self, mode=None, handle=None):

        if mode == 'raw':
            
            response = Response(self.render('raw'))
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


class Datapoint(poobrains.storage.Model):

    class Meta:
        order_by = ['dataset', 'x']
        primary_key = poobrains.storage.CompositeKey('dataset', 'x')

    dataset = poobrains.storage.fields.ForeignKeyField(Dataset, related_name='datapoints')
    x = poobrains.storage.fields.DoubleField()
    y = poobrains.storage.fields.DoubleField()
    error_lower = poobrains.storage.fields.FloatField(help_text="Lower margin of error", default=0.0)
    error_upper = poobrains.storage.fields.FloatField(help_text="Upper margin of error", default=0.0)


@app.expose('/svg/plot')
class Plot(SVG):

    datasets = None
    min_x = None
    max_x = None
    min_y = None
    max_y = None

    def __init__(self, handle=None, mode=None, **kwargs):

        super(Plot, self).__init__(**kwargs)
        self.datasets = []

        if handle is None:
            abort(404)

        dataset_names = handle.split(',')

        for name in dataset_names:
            self.datasets.append(Dataset.load(name))

        
        #all_datapoints = [dp for dp in ds.datapoints for ds in self.datasets]
        all_datapoints = []
        for dataset in self.datasets:
            for datapoint in dataset.datapoints:
                all_datapoints.append(datapoint)

        self.min_x = min([dp.x for dp in all_datapoints])
        self.max_x = max([dp.x for dp in all_datapoints])
        self.min_y = min([dp.y for dp in all_datapoints])
        self.max_y = max([dp.y for dp in all_datapoints])

    def normalize_x(self, value):

        span = self.max_x - self.min_x
        if span == 0.0:
            return 50

        return (value - self.min_x) * (100 / span)


    def normalize_y(self, value):

        span = self.max_y - self.min_y
        if span == 0.0:
            return 50

        return (value - self.min_y) * (100 / span)

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

    dataset = poobrains.storage.fields.ForeignKeyField(MapDataset, related_name='datapoints')
    title = poobrains.storage.fields.CharField()
    description = poobrains.md.MarkdownField(null=True)
    latitude = poobrains.storage.fields.DoubleField()
    longitude = poobrains.storage.fields.DoubleField()


    # mercator calculation shamelessly thieved from the osm wiki
    # http://wiki.openstreetmap.org/wiki/Mercator

    @property
    def x(self):

        if not self.longitude is None:
            r_major=6378137.000
            return r_major*math.radians(self.longitude)


    @property
    def y(self):

        if not self.latitude is None:

            if self.latitude>89.5:self.lat=89.5
            if self.latitude<-89.5:self.latitude=-89.5
            r_major=6378137.000
            r_minor=6356752.3142
            temp=r_minor/r_major
            eccent=math.sqrt(1-temp**2)
            phi=math.radians(self.latitude)
            sinphi=math.sin(phi)
            con=eccent*sinphi
            com=eccent/2
            con=((1.0-con)/(1.0+con))**com
            ts=math.tan((math.pi/2-phi)/2)/con
            y=0-r_major*math.log(ts)
            return y


@app.expose('/svg/map')
class Map(SVG):

    datasets = None

    def __init__(self, handle=None, mode=None, **kwargs):
        
        super(Map, self).__init__(handle=handle, mode=mode, **kwargs)
        self.datasets = []

        if handle is None:
            abort(404)

        dataset_names = handle.split(',')

        for name in dataset_names:
            self.datasets.append(MapDataset.load(name))

for cls in set([SVG]).union(SVG.class_children()):
    rule = os.path.join("/svg/", cls.__name__.lower(), '<handle>', 'raw')
    app.site.add_view(cls, rule, mode='raw')
