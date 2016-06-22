import collections

import poobrains

class Permission(poobrains.helpers.ChildAware):
   
    instance = None
    label = NOne
    choices = [('grant', 'For all instances'), ('deny', 'Explicitly deny')]

    class Meta:
        abstract = True

    def __init__(self, instance):
        self.instance = instance
        self.check = self.instance_check

    @classmethod
    def check(cls, user):
        return user.access(cls)

    def instance_check(self, user):
        pass


class OwnedPermission(Permission):
    choices = [('all', 'For all instances'), ('own', 'For own instances'), ('deny', 'Explicitly deny')]


class PermissionInjection(poobrains.helpers.MetaCompatibility): # TODO: probably not going to use this after all; if so, get rid of it

    def __new__(cls, name, bases, attrs):

        cls = super(PermissionInjection, cls).__new__(cls, name, bases, attrs)
        cls.permissions = collections.OrderedDict()

        for mode in cls._meta.modes:
            perm_name = "%s_%s" % (cls.__name__, mode)
            perm_label = "%s %s" % (mode.capitalize(), cls.__name__)
            cls.permissions[mode] = type(perm_name, (Permission,), {})

        return cls
