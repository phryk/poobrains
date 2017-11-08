# -*- coding: utf-8 -*-

import poobrains.rendering
import poobrains.storage
import poobrains.commenting

class SVG(poobrains.rendering.Renderable):
    
    style = None

    def __init__(self, name=None, css_class=None):

        self.style = self.scss_compiler.compile_string("@import 'svg';")


class Dataset(poobrains.commenting.Commentable):

    title = poobrains.storage.fields.CharField()
    description = poobrains.md.MarkdownField(null=True)
    x_label = poobrains.storage.fields.CharField(verbose_name="Label for the x-axis")
    y_label = poobrains.storage.fields.CharField(verbose_name="Label for the y-axis")


class Datapoint(poobrains.storage.Model):

    dataset = poobrains.storage.fields.ForeignKeyField(Dataset)
    x = poobrains.storage.fields.DoubleField()
    y = poobrains.storage.fields.DoubleField()
    error_upper = poobrains.storage.fields.FloatField(verbose_name="Upper margin of error")
    error_lower = poobrains.storage.fields.FloatField(verbose_name="Lower margin of error")
