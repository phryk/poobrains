# -*- coding: utf-8 -*-

"""
    Form/CLI types for coercion/validation

    NOTE:   Other modules inject properties into this module
            Not everything in form.types comes from click.types!
"""

import datetime

from click.types import * # You thought I wrote code for this? :>

from poobrains import app

class DateParamType(ParamType):

    format = None

    def __init__(self, format='%Y-%m-%d'):

        super(DateParamType, self).__init__()
        self.format = format


    def convert(self, value, param, ctx):

        if value == '':
            return None

        if isinstance(value, datetime.date):
            return value # apparently we need this function to be idempotent.

        try:
            return datetime.datetime.strptime(value, self.format).date()

        except ValueError as e:

            if "does not match format" in e.message:

                app.logger.error("%s.convert failed: %s" % (type(e).__name__, e.message))
                self.fail("We dun goof'd, this field isn't working.")

            else:

                self.fail("'%s' is not a valid date. Expected format: %s" % (value, self.format))

DATE = DateParamType()


class DateTimeParamType(ParamType):

    format = None

    def __init__(self, format='%Y-%m-%d %H:%M:%S'):

        super(DateTimeParamType, self).__init__()
        self.format = format


    def convert(self, value, param, ctx):

        if value == '':
            return None

        if isinstance(value, datetime.datetime):
            return value # apparently we need this function to be idempotent.

        try:
            return datetime.datetime.strptime(value, self.format)

        except ValueError as e:

            if "does not match format" in e.message:

                app.logger.error("%s.convert failed: %s" % (type(e).__name__, e.message))
                self.fail("We dun goof'd, this field isn't working.")

            else:

                self.fail("'%s' is not a valid datetime. Expected format: %s" % value, self.format)

DATETIME = DateTimeParamType()
