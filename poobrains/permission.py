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

        if not (user.own_permissions.has_key(cls.__name__) and user.own_permissions[cls.__name__] == 'grant'):
            poobrains.app.logger.warning("Access denied to user '%s'. Inadequate access for permission '%s'." % (user.name, cls.__name__))
            raise PermissionDenied("YOU SHALL NOT PASS!")


    def instance_check(self, user):
        return self.__class__.check(user)


class OwnedPermission(Permission):
    choices = [('all', 'For all instances'), ('own', 'For own instances'), ('deny', 'Explicitly deny')]
    
    class Meta:
        abstract = True

    @classmethod
    def check(cls, user):
        # TODO: get Owned instance in here to check for 'own' access.
        if not (user.own_permissions.has_key(cls.__name__) and user.own_permissions[cls.__name__] == 'all'):
            poobrains.app.logger.warning("Access denied to user '%s'. Inadequate access for permission '%s'." % (user.name, cls.__name__))
            raise PermissionDenied("YOU SHALL NOT PASS!")


#    def instance_check(self, user):
#        raise NotImplementedError('yoink')


class PermissionInjection(poobrains.helpers.MetaCompatibility): # TODO: probably not going to use this after all; if so, get rid of it

    def __new__(cls, name, bases, attrs):
        
        cls = super(PermissionInjection, cls).__new__(cls, name, bases, attrs)
        #cls._meta.permissions = collections.OrderedDict()
        cls.permissions = collections.OrderedDict()

        for mode in cls._meta.modes:
            perm_name = "%s_%s" % (cls.__name__, mode)
            perm_label = "%s %s" % (mode.capitalize(), cls.__name__)
            #cls._meta.permissions[mode] = type(perm_name, (cls._meta.permission_class,), {})
            perm_attrs = dict()

            if hasattr(cls._meta, 'abstract') and cls._meta.abstract:

                # Make permissions belonging to abstract Renderables abstract as well
                #FIXME: I have no clue why both _meta and Meta are needed, grok it, simplify if sensible

                meta = poobrains.helpers.FakeMetaOptions()
                meta.abstract = True
                perm_attrs['_meta'] = meta

                class Meta:
                    abstract = True

                perm_attrs['Meta'] = Meta
            
            cls.permissions[mode] = type(perm_name, (cls._meta.permission_class,), perm_attrs)

        return cls
