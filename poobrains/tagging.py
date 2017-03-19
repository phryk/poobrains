# -*- coding: utf-8 -*-

import collections
import peewee
import flask

import poobrains

@poobrains.app.expose('/tag/', mode='full')
class Tag(poobrains.auth.Named):

    description = poobrains.storage.fields.TextField()
    parent = poobrains.storage.fields.ForeignKeyField('self', null=True, constraints=[peewee.Check('parent_id <> id')])


    class Meta:

        modes = collections.OrderedDict([
            ('add', 'c'),
            ('teaser', 'r'),
            ('full', 'r'),
            ('edit', 'u'),
            ('delete', 'd')
        ])


    @classmethod
    def tree(cls, root=None):
        
        tree = collections.OrderedDict()
        
        tags = cls.select().where(cls.parent == root)
        for tag in tags:
            tree[tag.name] = cls.tree(tag)

        return tree


    def list_tagged(self):

        bindings = TagBinding.select().where(TagBinding.tag == self).limit(poobrains.app.config['PAGINATION_COUNT'])
        bindings_by_model = collections.OrderedDict()
        contents = []

        for binding in bindings:

            if not bindings_by_model.has_key(binding.model):
                bindings_by_model[binding.model] = []

            bindings_by_model[binding.model].append(binding)

        #bindings_by_model = sorted(bindings_by_model) # re-order by model name

        for model_name, bindings in bindings_by_model.iteritems():

            try:
                model = poobrains.storage.Storable.children_keyed()[model_name]
            except KeyError:
                poobrains.app.logger.error("TagBinding for unknown model: %s" % model_name)
                continue

            #handle_fields = [getattr(model, field_name) for field_name in model._meta.handle_fields]
            handles = [model.string_handle(binding.handle) for binding in bindings]
            query = model.list('r', user=flask.g.user, handles=handles)
            contents.extend(query)
            #pkfields = model._meta.get_primary_key_fields()

            #pkvalues = []
            #for handle in handles:
            #    pkvalues.append(model.string_handle(handle))


        return contents



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

        if kwargs.has_key('choices'):
            choices = kwargs.pop('choices')
        else:
            choices = []

            try:
                for tag in Tag.select():
                    choices.append((tag.name, tag.name))

            except peewee.OperationalError as e:
                poobrains.app.logger.error("Failed building list of tags for TaggingField: %s" % e.message)

        self.choices = choices


class TaggingFieldset(poobrains.form.Fieldset):

    tags = TaggingField('tags')

    def __init__(self, instance):

        super(TaggingFieldset, self).__init__()
        if instance._get_pk_value() != None:
           self.fields['tags'].value = [tag.name for tag in instance.tags] 


    def handle(self, instance):
        
        q = TagBinding.delete().where(TagBinding.model == instance.__class__.__name__, TagBinding.handle == instance.handle_string).execute()
        for value in self.fields['tags'].value:
            try:
                tag = Tag.load(value)
            except Tag.DoesNotExist:
                flask.flash("No such tag: %s" % unicode(value))
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
