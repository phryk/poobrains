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

    def convert(self, value, param, ctx):

        if value == '':
            return None

        if isinstance(value, datetime.date):
            return value # apparently we need this function to be idempotent.

        try:
            return datetime.datetime.strptime(value, '%Y-%m-%d').date()

        except ValueError as e:

            if "does not match format" in e.message: # TODO: find out what this means again and comment it

                app.logger.error("%s.convert failed: %s" % (type(e).__name__, e.message))
                self.fail("We dun goof'd, this field isn't working.")

            else:

                self.fail("'%s' is not a valid date. Expected format: %Y-%m-%d" % value)

DATE = DateParamType()


class DateTimeParamType(ParamType):

    def convert(self, value, param, ctx):

        if value == '':
            return None

        if isinstance(value, datetime.datetime):
            return value # apparently we need this function to be idempotent.

        try:
            return datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S')

        except ValueError as e:

            if "does not match format" in e.message:

                app.logger.error("%s.convert failed: %s" % (type(e).__name__, e.message))
                self.fail("We dun goof'd, this field isn't working.")

            else:

                try:
                    return datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f')

                except ValueError as e:

                if "does not match format" in e.message:

                    app.logger.error("%s.convert failed: %s" % (type(e).__name__, e.message))
                    self.fail("We dun goof'd, this field isn't working.")

                else:
                    self.fail("'%s' is not a valid datetime. Expected format '%Y-%m-%d %H:%M:%S' or '%Y-%m-%d %H:%M:%S.%f'" % value)

DATETIME = DateTimeParamType()
