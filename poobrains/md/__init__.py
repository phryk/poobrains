# -*- coding: utf-8 -*-

import collections
import peewee
import jinja2
import markdown

import flask

# local imports
from poobrains import app
import poobrains.rendering
import poobrains.storage
#import poobrains.auth


def magic_markdown_loader(storable, handle):

    storables = poobrains.storage.Storable.class_children_keyed(lower=True)

    cls = storables[storable.lower()]
    return cls.load(handle)


class MarkdownString(unicode):

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


class DisplayRenderable(markdown.inlinepatterns.Pattern):

    def handleMatch(self, match):

        if match:

            cls_name = match.group(2).lower()
            handle = match.group(3)

            renderables = poobrains.rendering.Renderable.class_children_keyed(lower=True)

            if cls_name in renderables:

                cls = renderables[cls_name.lower()]
                try:

                    if issubclass(cls, poobrains.storage.Storable):
                        instance = cls.load(handle)

                    else:
                        instance = cls(handle=handle)

                    #if isinstance(instance, poobrains.auth.Protected):
                    if hasattr(instance, 'permissions'):

                        try:
                            instance.permissions['read'].check(flask.g.user)
                        
                        except:
                            return jinja2.Markup(md.convert("*You are not allowed to view an instance of %s that was placed here.*" % cls.__name__))

                    if instance._meta.modes.has_key('inline'):
                        return instance.render('inline')
                    elif instance._meta.modes.has_key('teaser'):
                        return instance.render('teaser')
                    elif instance._meta.modes.has_key('full'):
                        return instance.render('full')
                    else:
                        return instance.render()

                except Exception:
                    pass # fall back to default handling (giving shit back unchanged)

            return match.group(0)

        return super(DisplayRenderable, self).handleMatch(match)


class DisplayRenderableExtension(markdown.Extension):

    def extendMarkdown(self, md, md_globals):

        md.inlinePatterns.add(
            self.__class__.__name__,
            DisplayRenderable('!\[(.*?)/(.*?)]'),
            '<reference'
        )


md = app.config['MARKDOWN_CLASS'](
    output_format=app.config['MARKDOWN_OUTPUT'],
    extensions=[DisplayRenderableExtension()] + app.config['MARKDOWN_EXTENSIONS']
)

md.references.set_loader(magic_markdown_loader)
