import collections
import werkzeug


import poobrains


class PermissionDenied(werkzeug.exceptions.HTTPException):
    code = 403


class Permission(poobrains.helpers.ChildAware):
   
    instance = None
    label = None
    choices = [('grant', 'For all instances'), ('deny', 'Explicitly deny')]

    class Meta:
        abstract = True

    def __init__(self, instance):
        self.instance = instance
        self.check = self.instance_check

    @classmethod
    def check(cls, user):

        if not (user.permissions.has_key(cls.__name__) and user.permissions[cls.__name__] == 'grant'):
            raise PermissionDenied("YOU SHALL NOT PASS!")


    def instance_check(self, user):
        raise NotImplementedError("Wait, we actually instantiate Permissions?")


class OwnedPermission(Permission):
    choices = [('all', 'For all instances'), ('own', 'For own instances'), ('deny', 'Explicitly deny')]


class PermissionInjection(poobrains.helpers.MetaCompatibility): # TODO: probably not going to use this after all; if so, get rid of it

    def __new__(cls, name, bases, attrs):
        print "PermissionInjection: ", name
        cls = super(PermissionInjection, cls).__new__(cls, name, bases, attrs)
        cls._meta.permissions = collections.OrderedDict()

        for mode in cls._meta.modes:
            perm_name = "%s_%s" % (cls.__name__, mode)
            perm_label = "%s %s" % (mode.capitalize(), cls.__name__)
            cls._meta.permissions[mode] = type(perm_name, (cls._meta.permission_class,), {})

        return cls
