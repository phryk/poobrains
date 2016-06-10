# -*- coding: utf-8 -*-
# Yes, it's actually "coercers", I looked it up.

def coerce_string(field, value):
    return unicode(value)

def coerce_int(field, value):
    return int(value)

def coerce_float(field, value):
    return float(value)

def coerce_bool(field, value):
    print "::::::::::::::::::::::::::::::::::::::::::::::::: coercing bool", value, bool(int(value))
    return bool(int(value))
