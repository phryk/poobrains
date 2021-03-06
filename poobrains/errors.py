# -*- coding: utf-8 -*-

from click.exceptions import BadParameter

class ExposedError(Exception):
    pass


class ValidationError(ExposedError):
    
    def __init__(self, msg, field=None):

        self.field = field
        super(ExposedError, self).__init__(msg)


class CompoundError(ValidationError):

    errors = None

    def __init__(self, errors=None):

        if not errors is None:
            self.errors = errors
        else:
            self.errors = []


    @property
    def message(self):
        msg = "There were %d errors." % len(self.errors)

        for error in self.errors:
            msg += "\n"+error.message

        return msg


    def append(self, value):
        self.errors.append(value)


    def __len__(self):
        return self.errors.__len__()


    def __iter__(self):
        return self.errors.__iter__()
