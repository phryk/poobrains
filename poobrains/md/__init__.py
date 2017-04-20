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


md = poobrains.app.config['MARKDOWN_CLASS'](
    output_format=poobrains.app.config['MARKDOWN_OUTPUT'],
    extensions=poobrains.app.config['MARKDOWN_EXTENSIONS']
)

md.references.set_loader(magic_markdown_loader)


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

            cls_name = match.group(1).lower()
            handle = match.group(2)

            renderables = collections.OrderedDict([(k.lower(), v) for k, v in poobrains.rendering.Renderable.children_keyed().iteritems])

            if cls_name in renderables:

                cls = renderables[cls_name]
                try:

                    if issubclass(cls, poobrains.storage.Storable):
                        instance = cls.load(handle)

                    else:
                        instance = cls(handle=handle)

                except Exception:
                    pass # fall back to default handling (giving shit back unchanged)

            return match.group(0)

        return super(DisplayRenderable, self).handleMatch(match)


class DisplayRenderableExtension(markdown.Extension):

    def extendMarkdown(self, md, md_globals):

        md.inlinePatterns.add(self.__class__.__name__, DisplayRenderable('!\[(.*?):(.*?)]', self.__class__.__name__, '<reference')
