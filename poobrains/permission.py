import collections
import werkzeug


import poobrains


class PermissionDenied(werkzeug.exceptions.HTTPException):
    code = 403


class Permission(poobrains.helpers.ChildAware):
   
    instance = None
    mode = None
    label = None
    choices = [('grant', 'Grant'), ('deny', 'Explicitly deny')]

    class Meta:
        abstract = True

    def __init__(self, instance):
        self.instance = instance
        self.check = self.instance_check

    @classmethod
    def check(cls, user):

        # check user-assigned permission state
        if user.own_permissions.has_key(cls.__name__):
            access = user.own_permissions[cls.__name__]

            if access == 'deny':
                raise PermissionDenied("YOU SHALL NOT PASS!")

            elif access == 'grant':
                return True

        # check if user is member of any groups with 'deny' for this permission
        group_deny = GroupPermission.select().join(Group).join(UserGroup).join(User).where(Group.user == user, GroupPermission.permission == cls.__name__, GroupPermission.access == 'deny').count()

        if group_deny:
            raise PermissionDenied("YOU SHALL NOT PASS!")

        group_grant = GroupPermission.select().join(Group).join(UserGroup).join(User).where(Group.user == user, GroupPermission.permission == cls.__name__, GroupPermission.access == 'grant').count()

        if group_grant:
            return True

        raise PermissionDenied("YOU SHALL NOT PASS!")



    def instance_check(self, user):
        return self.__class__.check(user)


class PermissionInjection(poobrains.helpers.MetaCompatibility):

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
                perm_attrs['mode'] = mode

                class Meta:
                    abstract = True

                perm_attrs['Meta'] = Meta
            
            cls.permissions[mode] = type(perm_name, (cls._meta.permission_class,), perm_attrs)

        return cls
