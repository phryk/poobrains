# -*- coding: utf-8 -*-

import peewee
import poobrains

print "WTFBRAINS:", poobrains, dir(poobrains)

class StorableParam(poobrains.cli.StringParam):

    def parse(self, value):

        storables = poobrains.storage.Storable.children_keyed()

        if self.optional and value is None:
            return None

        if not value in storables.keys():
            raise InvalidValue("Not a known storable: %s. Take one of these: %s" % (value, ', '.join(storables.keys())))

        return value


class List(poobrains.cli.Command):

    storable = StorableParam()

    def execute(self):

        storables = poobrains.storage.Storable.children_keyed()

        storable = storables[self.values['storable']]
        for instance in storable.select():
            print "[%d][%s] %s" % (instance.id, instance.name, instance.title)


class Add(poobrains.cli.Command):

    #params = {'storable': coerce_storable, 'id_or_name': 'coerce_string'}
    storable = StorableParam()

    def execute(self):
        
        if self.storables.has_key(self.values['storable']):

            cls = self.storables[self.values['storable']]
            instance = cls()

            stdout.write("Addding %s...\n" % (cls.__name__,))
            for field in cls._meta.get_fields():

                if not isinstance(field, peewee.PrimaryKeyField):
                    stdout.write("%s: " % (field.name,))
                    value = raw_input()

                    setattr(instance, field.name, value) # TODO type enforcement

            instance.save()
