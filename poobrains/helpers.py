from collections import OrderedDict


class TrueDict(OrderedDict):

    def __setitem__(self, key, value):

        if value == True and True in self.itervalues() and self[name] != True:
            raise ValueError('Only one item may be True.')

        return super(TrueDict, self).__setitem__(key, value)


    def choose(self):

        if True in self.values():
            for choice, primary in self.iteritems():
                if primary == True:
                    break
        else:
            choice = self.keys()[0]

        return choice
