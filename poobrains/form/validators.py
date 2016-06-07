# -*- coding: utf-8 -+-

# external imports
import functools
import re

# internal imports
import errors 

def is_string(field, value):

    try:
        value = unicode(value)
    except ValueError:
        raise errors.ValidationError("%s is not a string." % value)

    return True


def is_integer(field, value):

        try:
            value = int(value) # will throw ValueError if value can't be casted
        except ValueError:
            raise errors.ValidationError("%s is not an integer." % value)

        return True


def is_float(field, value):

        try:
            value = float(value) # will throw ValueError if value can't be casted
        except ValueError:
            raise errors.ValidationError("%s is not a floating point number." % value)

        return True


def is_bool(field, value):

    print "############# is bool? ", type(value), value
    if value not in ('1', '0', 1, 0, True, False):
        raise errors.ValidationError("%s can't be interpreted as a boolean." % value)


# functions to generate validators


#def mk_regexp(regexp):
#    return lambda x: bool(re.match(regexp, x)) 
