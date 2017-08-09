# -*- coding: utf-8 -*-

import collections
import peewee
import flask

#import poobrains
from poobrains import app
import poobrains.helpers
import poobrains.rendering
import poobrains.form
import poobrains.storage
import poobrains.auth
import poobrains.md


#@app.expose('/tag/', mode='full')
class Tag(poobrains.auth.Named):

    title = poobrains.storage.fields.CharField()
    parent = poobrains.storage.fields.ForeignKeyField('self', null=True, constraints=[peewee.Check('parent_id <> id')]) # FIXME: Yes, this is no proper protection against loops
    description = poobrains.md.MarkdownField()

    offset = None


    class Meta:

        modes = collections.OrderedDict([
            ('add', 'create'),
            ('teaser', 'read'),
            ('inline', 'read'),
            ('full', 'read'),
            ('edit', 'update'),
            ('delete', 'delete')
        ])


    def __init__(self, *args, **kwargs):

        super(Tag, self).__init__(*args, **kwargs)
        self.offset = 0
    
    
    @classmethod
    def class_tree(cls, root=None, current_depth=0):
       
        if current_depth == 0:
            tree = poobrains.rendering.Tree(root=poobrains.rendering.RenderString(root.name), mode='inline')
        else:
            tree = poobrains.rendering.Tree(root=root, mode='inline')

        if current_depth > 100:

            if root:
                message = "Possibly incestuous tag: '%s'."  % root.name
            else:
                message = "Possibly incestuous tag, but don't have a root for this tree. Are you fucking with current_depth manually?"

            app.logger.error(message)
            return tree 

        tags = cls.select().where(cls.parent == root)

        for tag in tags:
            tree.children.append(tag.tree(current_depth=current_depth+1))

        return tree


    def tree(self, current_depth=0):

        return self.__class__.class_tree(root=self, current_depth=current_depth)


    @poobrains.auth.protected
    @poobrains.helpers.themed
    def view(self, mode=None, handle=None, offset=0):

        """
        view function to be called in a flask request context
        """
        
        if mode in ('add', 'edit', 'delete'):

            f = self.form(mode)
            return poobrains.helpers.ThemedPassthrough(f.view('full'))

        self.offset = offset
        return self


    def list_tagged(self):

        bindings = TagBinding.select().where(TagBinding.tag == self).limit(app.config['PAGINATION_COUNT'])
        bindings_by_model = collections.OrderedDict()
        queries = []

        for binding in bindings:

            if not bindings_by_model.has_key(binding.model):
                bindings_by_model[binding.model] = []

            bindings_by_model[binding.model].append(binding)

        #bindings_by_model = sorted(bindings_by_model) # re-order by model name

        for model_name, bindings in bindings_by_model.iteritems():

            try:
                model = poobrains.storage.Storable.class_children_keyed()[model_name]
            except KeyError:
                app.logger.error("TagBinding for unknown model: %s" % model_name)
                continue

            handles = [model.string_handle(binding.handle) for binding in bindings]
            queries.append(model.list('read', user=flask.g.user, handles=handles))


        pagination = poobrains.storage.Pagination(queries, self.offset, 'site.tag_handle_offset')

        return pagination

    def save(self, *args, **kwargs):
        if not self.title:
            self.title = self.name.replace('-', ' ').title()

        return super(Tag, self).save(*args, **kwargs)

app.site.add_listing(Tag, '/tag/', mode='teaser', endpoint='tag')
app.site.add_view(Tag, '/tag/<handle>/', mode='full', endpoint='tag_handle')
app.site.add_view(Tag, '/tag/<handle>/+<int:offset>', mode='full', endpoint='tag_handle_offset')


class TagBinding(poobrains.auth.Administerable):

    class Meta:
        order_by = ['-priority']

    tag = poobrains.storage.fields.ForeignKeyField(Tag, related_name='_bindings')
    model = poobrains.storage.fields.CharField()
    handle = poobrains.storage.fields.CharField()
    priority = poobrains.storage.fields.IntegerField()


class TaggingField(poobrains.form.fields.MultiChoice):
    
    def __init__(self, *args, **kwargs):

        super(TaggingField, self).__init__(*args, **kwargs)

        choices = []

        try:
            for tag in Tag.select():
                choices.append((tag.name, tag.name))

        except (peewee.OperationalError, peewee.ProgrammingError) as e:
            app.logger.error("Failed building list of tags for TaggingField: %s" % e.message)

        self.choices = choices


class TaggingFieldset(poobrains.form.Fieldset):

    tags = TaggingField('tags')

    def __init__(self, instance):

        super(TaggingFieldset, self).__init__()
        if instance._get_pk_value() != None:
           self.fields['tags'].value = [tag.name for tag in instance.tags] 


    def process(self, instance):
        
        q = TagBinding.delete().where(TagBinding.model == instance.__class__.__name__, TagBinding.handle == instance.handle_string).execute()
        for value in self.fields['tags'].value:
            try:
                tag = Tag.load(value)
            except Tag.DoesNotExist:
                flask.flash(u"No such tag: %s" % unicode(value))
                return # TODO: We want to raise a type of exception we know is okay to print (preventing infoleak)

            binding = TagBinding()
            binding.tag = tag
            binding.model = instance.__class__.__name__
            binding.handle = instance.handle_string
            binding.priority = 42 # FIXME
            binding.save()


class Taggable(poobrains.auth.NamedOwned):

    tags = None

    class Meta:
        abstract = True


    def __init__(self, *args, **kwargs):
        super(Taggable, self).__init__(*args, **kwargs)
        self.tags = []

    def form(self, mode=None):

        f = super(Taggable, self).form(mode=mode)
        if mode != 'delete':
            setattr(f, 'tags', TaggingFieldset(self))
        return f


    def prepared(self):

        super(Taggable, self).prepared()
        bindings = TagBinding.select().where(TagBinding.model == self.__class__.__name__, TagBinding.handle == self.handle_string)

        for binding in bindings:
            self.tags.append(binding.tag)
