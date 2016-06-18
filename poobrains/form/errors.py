# -*- coding: utf-8 -*-

class ValidationError(Exception):
    pass


class BindingError(Exception): # If we have CoercionError, is this even needed?
    pass


class CoercionError(Exception):
    pass


class MissingValue(Exception):
    pass

class CompoundError(Exception):

    errors = None

    def __init__(self):
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
        return len(self.errors)
