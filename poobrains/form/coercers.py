# -*- coding: utf-8 -*-
# Yes, it's actually "coercers", I looked it up.

import datetime

def coerce_string(field, value):
    return unicode(value)

def coerce_int(field, value):
    return int(value)

def coerce_float(field, value):
    return float(value)

def coerce_bool(field, value):
    if isinstance(value, basestring) and value.isdigit():
        return bool(int(value))
    return bool(value)


def coerce_datetime(field, value):

    return datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
