# -*- coding: utf-8 -*-

import collections
import peewee

import poobrains

class Tag(poobrains.auth.Named):

    description = poobrains.storage.fields.TextField()
    parent = poobrains.storage.fields.ForeignKeyField('self', null=True, constraints=[peewee.Check('parent_id <> id')])

    def list_tagged(self):

        poobrains.app.debugger.set_trace()
        bindings = TagBinding.select().where(TagBinding.tag == self).limit(poobrains.app.config['PAGINATION_COUNT'])
        bindings_by_model = collections.OrderedDict()

        for binding in bindings:

            if not bindings_by_model.has_key(binding.model):
                bindings_by_model[binding.model] = []

            bindings_by_model[binding.model].append(binding)

        bindings_by_model = sort(bindings_by_model) # re-order by model name

        for model_name, handles in bindings_by_model.iteritems():

            model = poobrains.storage.Storable.children_keyed(model_name)
            pkfields = model._meta.get_primary_key_fields()

            pkvalues = []
            for handle in handles:
                pkvalues.append(model.string_handle(handle))

            instances = model.select()



class TagBinding(poobrains.auth.Administerable):

    tag = poobrains.storage.fields.ForeignKeyField(Tag, related_name='_bindings')
    model = poobrains.storage.fields.CharField()
    handle = poobrains.storage.fields.CharField()
    priority = poobrains.storage.fields.IntegerField()



