# -*- coding: utf-8 -+-

# external imports
import re


def is_int(value):

        try:
            value = int(value) # will throw ValueError if value can't be casted
        except ValueError:
            return False

        return True


def is_float(value):

        try:
            value = float(value) # will throw ValueError if value can't be casted
        except ValueError:
            return False

        return True


def is_bool(value):
    return value == '1' or value == '0' # TODO: do we need to handle '' as well?


# functions to generate validators


def mk_min(min):
    return lambda x: x >= min


def mk_max(max):
    return lambda x: x <= max


def mk_regexp(regexp):
    return lambda x: bool(re.match(regexp, x)) 
