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

    if storable.lower() in storables:
        cls = storables[storable.lower()]
        return cls.load(handle)

    else:
        renderables = poobrains.rendering.Renderable.class_children_keyed(lower=True)
        cls = renderables[storable.lower()]
        return cls(handle=handle) # we could try handling Renderables without handle, but I think it's needed for expose anyways.

    return False


class MarkdownString(str):

    def render(self, mode='inline'): # mode is ignored anyways
        return jinja2.Markup(md.convert(self))


class MarkdownFieldAccessor(peewee.FieldAccessor):

    def __set__(self, instance, value):

        if not isinstance(value, MarkdownString):
            value = MarkdownString(value)

        super(MarkdownFieldAccessor, self).__set__(instance, value)


class MarkdownField(poobrains.storage.fields.TextField):

    accessor_class = MarkdownFieldAccessor

poobrains.storage.fields.MarkdownField = MarkdownField


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
                    if 'inline' in instance._meta.modes:
                        return instance.render('inline')
                    elif 'teaser' in instance._meta.modes:
                        return instance.render('teaser')
                    elif 'full' in instance._meta.modes:
                        return instance.render('full')
                    else:
                        return instance.render()

                except Exception as e:
                    app.logger.debug(e)
                    return jinja2.Markup(u'<span class="markdown-error">%s could not be loaded.</span>' % cls.__name__)

            else:
                return jinja2.Markup(u"<span class=\"markdown-error\">Don't know what %s is.</span>" % cls.__name__)

        return super(DisplayRenderable, self).handleMatch(match)


class DisplayRenderableExtension(markdown.Extension):

    def extendMarkdown(self, md, md_globals):

        md.inlinePatterns.add(
            self.__class__.__name__,
            DisplayRenderable('\!\[(.*?)/(.*?)]'),
            '<reference'
        )


md = app.config['MARKDOWN_CLASS'](
    output_format='xhtml5', # xml-style in order not to fuck too much with <foreignObject> HTML in SVG (see svg.Map for example)
    extensions=[DisplayRenderableExtension()] + app.config['MARKDOWN_EXTENSIONS']
)

md.references.set_loader(magic_markdown_loader)
