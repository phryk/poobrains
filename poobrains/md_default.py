# -*- coding: utf-8 -*-

import markdown

class MagicDict(dict):

    """ Magical dict to (try to) generate links on demand """

    loader = None

    def __init__(self, *args, **kwargs):

        super(MagicDict, self).__init__(*args, **kwargs)


    def __contains__(self, key):
        
        if not super(MagicDict, self).__contains__(key):

            if self._valid_magickey(key):
                
                storable, handle = key.split('/')
                try:
                    return bool(self.loader(storable, handle))
                except:
                    return False

            return False

        return True
    
    
    def __getitem__(self, key):

        if not super(MagicDict, self).__contains__(key):

            if self._valid_magickey(key):

                storable, handle = key.split('/')
                try:
                    instance = self.loader(storable, handle)

                    try:
                        url = instance.url('full')
                    except:

                        try:
                            url = instance.url('raw')
                        except:

                            try:
                                url = instance.url('teaser')
                            except:
                                url = "#NOLINK" # FIXME: What's the more elegant version of this, again?
                    if hasattr(instance, 'reference_title'):
                        title = instance.reference_title
                    elif hasattr(instance, 'title'):
                        title = instance.title
                    elif hasattr(instance, 'description'):
                        title = instance.description
                    elif hasattr(instance, 'filename'):
                        title = instance.filename
                    elif hasattr(instance, 'name'):
                        title = instance.name
                    else:
                        title = None

                    return (url, title)

                except:
                    raise KeyError("Couldn't load '%s/%s'." % (storable, handle))


        return super(MagicDict, self).__getitem__(key)


    def _valid_magickey(self, key):

        return '/' in key and len(key.split('/')) == 2


    def set_loader(self, loader):
        self.loader = loader



class pooMarkdown(markdown.Markdown):

    def __init__(self, *args, **kwargs):
        
        super(pooMarkdown, self).__init__(*args, **kwargs)
        self.references = MagicDict()
