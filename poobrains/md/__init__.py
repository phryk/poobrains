# -*- coding: utf-8 -*-

import peewee
import jinja2

import poobrains


def magic_markdown_loader(storable, handle):

    storables = poobrains.storage.Storable.children_keyed()
    for k, v in storables.iteritems():
        storables[k.lower()] = v # Allows us to use the correct case, or just lowercase

    cls = storables[storable]
    return cls.load(handle)


md = poobrains.app.config['MARKDOWN_CLASS'](output_format=poobrains.app.config['MARKDOWN_OUTPUT'])
md.references.set_loader(magic_markdown_loader)


class MarkdownString(str):

    def render(self, mode='inline'): # mode is ignored anyways
        return jinja2.Markup(md.convert(self))


class MarkdownFieldDescriptor(peewee.FieldDescriptor):

    def __set__(self, instance, value):

        if not isinstance(value, MarkdownString):
            value = MarkdownString(value)
        instance._data[self.att_name] = value
        instance._dirty.add(self.att_name)


class MarkdownField(poobrains.storage.fields.TextField):

    def add_to_class(self, model_class, name):

        super(MarkdownField, self).add_to_class(model_class, name)
        setattr(model_class, name, MarkdownFieldDescriptor(self))
