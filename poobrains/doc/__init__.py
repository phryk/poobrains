# -*- coding: utf-8 -*-
"""
The documentation system.
"""

import __builtin__

import os
import re
import sys
import string
import codecs # needed to open files with utf-8 encoding
import collections
import inspect
import pkgutil
import pydoc
import jinja2

from poobrains import app, Response
import poobrains.errors
import poobrains.helpers
import poobrains.storage
import poobrains.auth
import poobrains.md


def clean(text):

    """ mainly for cleaning < and > from `Repr`s """

    return text.replace('<', '&lt;').replace('>', '&gt;')


class MDRepr(pydoc.TextRepr, object):

    def repr_string(self, x, level):
        return clean(super(MDRepr, self).repr_string(x, level))

    def repr1(self, x, level):
        return clean(super(MDRepr, self).repr1(x, level))


class PooDoc(pydoc.HTMLDoc, object):

    """
        FIXME: doc* functions need an extra "level" parameter so we can the fitting h[1-6]
        This required overriding the 'document' function, but can only be done once all doc*
        functions are implemented.
    """


    level_offset = None
    local = None
    index_url = None

    def __init__(self, level_offset=0, local=False, index_url='/doc/'): 

        self.level_offset = level_offset
        self.local = local
        self.index_url = index_url

    
    # some utility functions first


    def getdoc(self, object):
        return poobrains.md.md.convert(pydoc.getdoc(object))


    def heading(self, level, content):

        """ Create a HTML heading """

        level += self.level_offset
        if level > 6:
            level = 6 # HTML headings only go from h1 to h6

        return "<h%d>%s</h%d>" % (level, content, level)
    
    
    def url(self, name):

        """ Create URL for a documentable thing. Mainly intended for subclassing """

        return "/doc/%s/" % name

    
    def listing(self, items, formatter=None):

        if formatter is not None:
            items = ['<li>' + formatter(item) + '</li>' for item in items]
        return '<ul class="list">%s</ul>' % ''.join(items) # <ul> might not be semantically correct, <ol> a better choice?


    def preformat(self, text):

        #return '<pre>%s</pre>' % text
        #return poobrains.md.md.convert(text)
        return text


    def modpkglink(self, data):
        """Make a link for a module or package to display in an index."""
        name, path, ispackage, shadowed = data
        if shadowed:
            return '<span class="shadowed">name</span>'
        if path:
            url = self.url('%s.%s' % (path, name))
        else:
            url = self.url(name)
        if ispackage:
            text = '<span class="package-name">%s</span> (package)' % name
        else:
            text = name
        return '<a href="%s">%s</a>' % (url, text)


    def modulelink(self, object):
        """Make a link for a module."""
        return '<a href="%s">%s</a>' % (self.url(object.__name__), object.__name__)


    def classlink(self, object, modname):
        """Make a link for a class."""
        name, module = object.__name__, sys.modules.get(object.__module__)
        if hasattr(module, name) and getattr(module, name) is object:
            return '<a href="%s#%s">%s</a>' % (
                self.url(module.__name__), name, pydoc.classname(object, modname))
        return pydoc.classname(object, modname)


    def formattree(self, tree, modname, parent=None):

        """Render in text a class tree as returned by inspect.getclasstree()."""

        result = '<ul class="tree">'
        for entry in tree:
            result += '<li>'
            if type(entry) is type(()): # means this is info about a class
                c, bases = entry
                result += '<span class="class-name">' + self.classlink(c, modname) + '</span>'

                if bases and bases != (parent,):
                    parents = map(lambda c, m=modname: pydoc.classname(c, m), bases)
                    result +=  '(<span class="bases">%s</span>)' % ', '.join(parents)

            elif type(entry) is type([]): # means this is a list of child classes of the previous item
                result += self.formattree(entry, modname, c)

            result += '</li>'

        result += '</ul>'

        return result


    def markup(self, text, escape=None, funcs={}, classes={}, methods={}):

        """Mark up some plain text, given a context of symbols to look for.
        Each context dictionary maps object names to anchor names.
        
        i.e. Replaces plaintext URLs with linked versions
        Also escapes input text

        """


        escape = escape or self.escape
        results = []
        here = 0
        pattern = re.compile(r'\b((http|ftp)://\S+[\w/]|'
                                r'RFC[- ]?(\d+)|'
                                r'PEP[- ]?(\d+)|'
                                r'(self\.)?(\w+))')

        while True:
            match = pattern.search(text, here)
            if not match: break
            start, end = match.span()
            results.append(escape(text[here:start]))

            all, scheme, rfc, pep, selfdot, name = match.groups()
            if scheme:
                url = escape(all).replace('"', '&quot;')
                results.append('<a href="%s" target="_blank" rel="noreferrer noopener">%s</a>' % (url, url))
            elif rfc:
                url = 'https://www.rfc-editor.org/rfc/rfc%d.txt' % int(rfc)
                results.append('<a href="%s" target="_blank" rel="noreferrer noopener">%s</a>' % (url, escape(all)))
            elif pep:
                url = 'https://www.python.org/dev/peps/pep-%04d/' % int(pep)
                results.append('<a href="%s" target="_blank" rel="noreferrer noopener">%s</a>' % (url, escape(all)))
            elif selfdot:
                # Create a link for methods like 'self.method(...)'
                # and use <strong> for attributes like 'self.attr'
                if text[end:end+1] == '(':
                    results.append('self.' + self.namelink(name, methods))
                else:
                    results.append('self.<strong>%s</strong>' % name)
            elif text[end:end+1] == '(':
                results.append(self.namelink(name, methods, funcs, classes))
            else:
                results.append(self.namelink(name, classes))
            here = end
        results.append(escape(text[here:]))
        return ''.join(results)


    # now the things doing the heavy lifting

    def docmodule(self, object, name=None, mod=None, *ignored):

        """Produce HTML5 documentation for a module object."""

        level = 1 # FIXME: use passed level in the future

        components = {} # where we're storing all components to be output
        name = object.__name__ # ignore the passed-in name. not passed in anyways?

        try:
            all = object.__all__
        except AttributeError:
            all = None

        parts = name.split('.')
        links = []

        for i in range(len(parts)-1):
            links.append(
                '<a href="%s">%s</a>' %
                (
                    self.url('.'.join(parts[:i+1])),
                    parts[i]
                )
            )

        head_link = '.'.join(links + parts[-1:])

        try:
            path = inspect.getabsfile(object)

            if self.local:
                url = path
                if sys.platform == 'win32': # in case i want to give this to the python project
                    import nturl2path
                    url = nturl2path.pathname2url(path)

                components['fileref'] = '<a class="file-reference" href="file:%s">%s</a>' % (url, path)

            else:
                components['fileref'] = '<span class="file-reference">%s</span>' % path

        except TypeError:
            components['fileref'] = '<span class="file-reference builtin">(built-in)</span>'

        info = []
        if hasattr(object, '__version__'):
            version = pydoc._binstr(object.__version__)
            if version[:11] == '$' + 'Revision: ' and version[-1:] == '$':
                version = strip(version[11:-1])
            info.append('version %s' % self.escape(version))
        if hasattr(object, '__date__'):
            info.append(self.escape(pydoc._binstr(object.__date__)))

        # build the main heading
        if info:
            components['head'] = self.heading(level + 1, '%s(<span class="info">%s)' % (head_link, ', '.join(info)))

        else:
            components['head'] = self.heading(level + 1, head_link) # heading which is a linked representation of the module "address"

        docloc = self.getdocloc(object) # get the official url of object, if any
        if docloc is not None:
            components['docloc'] = '<a class="official-docs" href="%s" target="_blank" rel="noreferrer noopener">Module Docs</a>' % docloc
        else:
            components['docloc'] = ''

        # collect modules, classes, functions and data in `object`

        modules = inspect.getmembers(object, inspect.ismodule)

        classes, cdict = [], {}
        for key, value in inspect.getmembers(object, inspect.isclass):
            # if __all__ exists, believe it.  Otherwise use old heuristic.
            if (all is not None or
                (inspect.getmodule(value) or object) is object):
                if pydoc.visiblename(key, all, object):
                    classes.append((key, value))
                    cdict[key] = cdict[value] = '#' + key # key used as URL fragment
        for key, value in classes:
            for base in value.__bases__:
                key, modname = base.__name__, base.__module__
                module = sys.modules.get(modname)
                if modname != name and module and hasattr(module, key):
                    if getattr(module, key) is base:
                        if not key in cdict:
                            cdict[key] = cdict[base] = self.url(modname) + '#' + key # key used as URL fragment

        funcs, fdict = [], {}
        for key, value in inspect.getmembers(object, inspect.isroutine):
            # if __all__ exists, believe it.  Otherwise use old heuristic.
            if (all is not None or
                inspect.isbuiltin(value) or inspect.getmodule(value) is object):
                if pydoc.visiblename(key, all, object):
                    funcs.append((key, value))
                    fdict[key] = '#-' + key
                    if inspect.isfunction(value): fdict[value] = fdict[key]

        data = []
        for key, value in inspect.getmembers(object, pydoc.isdata):
            if pydoc.visiblename(key, all, object):
                data.append((key, value))


        components['doc'] = self.getdoc(object) # build documentation for the thing passed in


        if hasattr(object, '__path__'):
            modpkgs = []
            for importer, modname, ispkg in pkgutil.iter_modules(object.__path__):
                modpkgs.append((modname, name, ispkg, 0))
            modpkgs.sort()
            components['modules'] = self.heading(level + 2, 'Package Contents') + self.listing(modpkgs, formatter=self.modpkglink)

        elif modules:
            components['modules'] = self.heading(level + 2, 'Modules') + self.listing([module for _, module in modules], formatter=self.modulelink)


        if classes:

            classlist = [cls for _, cls in classes]
            classtree = self.formattree(inspect.getclasstree(classlist, 1), name)

            classdocs = []
            for key, value in classes:
                classdocs.append(self.document(value, key, name, fdict, cdict))

            components['classes'] = self.heading(level + 2, 'Classes')
            components['classes'] += classtree
            components['classes'] += '<dl class="classes">'
            components['classes'] += '\n'.join(classdocs)
            components['classes'] += '</dl>'

        
        if funcs:

            docs = []
            for key, value in funcs:
                docs.append(self.document(value, key, name, fdict, cdict))

            components['funcs'] = self.heading(level + 2, 'Functions')
            components['funcs'] += '<dl class="functions">'
            components['funcs'] += '\n'.join(docs)
            components['funcs'] += '</dl>'


        if data:

            docs = []
            for key, value in data:
                docs.append(self.document(value, key))

            components['data'] = self.heading(level + 2, 'Data')
            components['data'] += '<dl class="data">'
            components['data'] += '\n'.join(docs)
            components['data'] += '</dl>'


        if hasattr(object, '__author__'):

            components['author'] = self.heading(level + 2, 'Author') + pydoc._binstr(object.__author__)


        if hasattr(object, '__credits__'):

            components['credits'] = self.geadubg(level + 2, 'Credits') + pydoc._binstr(object.__credits__)


        result = '%(head)s %(fileref)s %(docloc)s' % components
        result += '<div class="module">' % components
        result += '  <div class="docstring">%(doc)s</div>' % components

        if components.has_key('modules'):
            result += '  <div class="modules">%(modules)s</div>' % components

        if components.has_key('classes'):
            result += '  <div class="classes">%(classes)s</div>' % components

        if components.has_key('funcs'):
            result += '  <div class="functions">%(funcs)s</div>' % components

        if components.has_key('author'):
            result += '<div class="author">%(author)s</div>' % components

        if components.has_key('credits'):
            result += '<div class="credits">%(credits)s</div>' % components

        result += '</div>'

        return result


    def docclass(self, object, name=None, mod=None, funcs={}, classes={},
                 *ignored):
        """Produce HTML documentation for a class object."""
        
        level = 2 # FIXME: use passed level in the future

        realname = object.__name__
        name = name or realname
        bases = object.__bases__

        components = {}


        def spill(msg, attrs, predicate):
            ok, attrs = pydoc._split_list(attrs, predicate) # `ok` are attributes to handle, `attrs` is what's left
            if ok:
                result = msg
                for name, kind, homecls, value in ok:
                    try:
                        value = getattr(object, name)
                    except Exception:
                        # Some descriptors may meet a failure in their __get__.
                        # (bug #1785)
                        result += self._docdescriptor(name, value, mod)
                    else:
                        result += self.document(value, name, mod,
                                        funcs, classes, mdict, object)

                components['docs'].append(result) # NOTE: this is that important side-effect you're looking for!

            return attrs


        def spilldescriptors(msg, attrs, predicate):

            ok, attrs = pydoc._split_list(attrs, predicate) # `ok` are attributes to handle, `attrs` is what's left
            if ok:
                result = msg
                for name, kind, homecls, value in ok:
                    result += self._docdescriptor(name, value, mod)

                components['docs'].append(result) # NOTE: this is that important side-effect you're looking for!

            return attrs


        def spilldata(msg, attrs, predicate):
            ok, attrs = pydoc._split_list(attrs, predicate) # `ok` are attributes to handle, `attrs` is what's left
            if ok:

                result = msg
                for name, kind, homecls, value in ok:
                    base = self.docother(getattr(object, name), name, mod)
                    if (hasattr(value, '__call__') or
                            inspect.isdatadescriptor(value)):
                        doc = getattr(value, "__doc__", None)
                    else:
                        doc = None
                    if doc is None:
                        result += '<dl><dt>%s</dt></dl>\n' % base
                    else:
                        doc = self.markup(self.getdoc(value), self.preformat,
                                          funcs, classes, mdict)
                        doc = '<dd>%s</dd>' % doc
                        result += '<dl><dt>%s%s</dl>\n' % (base, doc)

                components['docs'].append(result) # NOTE: this is that important side-effect you're looking for!

            return attrs


        mro = collections.deque(inspect.getmro(object))
        if len(mro) > 2:
            components['mro'] = '<dl class="mro"><dt>Method resolution order:</dt>'
            for base in mro:
                components['mro'] += '<dd>%s</dd>' % self.classlink(base, object.__module__)
            components['mro'] += '</dl>'


        attrs = filter(lambda data: pydoc.visiblename(data[0], obj=object),
                       pydoc.classify_class_attrs(object))
        mdict = {}
        for key, kind, homecls, value in attrs:
            mdict[key] = anchor = '#' + name + '-' + key
            try:
                value = getattr(object, name)
            except Exception:
                # Some descriptors may meet a failure in their __get__.
                # (bug #1785)
                pass
            try:
                # The value may not be hashable (e.g., a data attr with
                # a dict or list value).
                mdict[value] = anchor
            except TypeError:
                pass


        components['docs'] = [] # populated in spill* functions

        while attrs:
            if mro:
                thisclass = mro.popleft()
            else:
                thisclass = attrs[0][2]
            attrs, inherited = pydoc._split_list(attrs, lambda t: t[2] is thisclass)

            if thisclass is __builtin__.object:
                attrs = inherited
                continue
            elif thisclass is object:
                tag = 'defined here:'
            else:
                tag = 'inherited from %s:' % self.classlink(thisclass,
                                                           object.__module__)

            # Sort attrs by name.
            try:
                attrs.sort(key=lambda t: t[0])
            except TypeError:
                attrs.sort(lambda t1, t2: cmp(t1[0], t2[0]))    # 2.3 compat

            attrs = spill('Methods %s' % tag, attrs,
                          lambda t: t[1] == 'method')
            attrs = spill('Class methods %s' % tag, attrs,
                          lambda t: t[1] == 'class method')
            attrs = spill('Static methods %s' % tag, attrs,
                          lambda t: t[1] == 'static method')
            attrs = spilldescriptors('Data descriptors %s' % tag, attrs,
                                     lambda t: t[1] == 'data descriptor')
            attrs = spilldata('Data and other attributes %s' % tag, attrs,
                              lambda t: t[1] == 'data')
            assert attrs == []
            attrs = inherited
        
        if name == realname:
            title = '<a name="%s" href="#%s">class <span class="class-name">%s</span></a>' % (
                name, name, realname)
        else:
            title = '<span class="class-name">%s</span> = <a name="%s" href="#%s>class %s</a>' % (
                name, name, name, realname)
        
        if bases:
            parents = []
            for base in bases:
                parents.append(self.classlink(base, object.__module__))
            title = title + '(%s)' % ', '.join(parents)

        result = '<dt class="class">%s</dt>' % self.heading(level, title)

        result += '<dd class="class">'
        if components.has_key('mro'):
            result += '  <div class="mro">%(mro)s</div>' % components

        result += '\n  '.join(components['docs'])

        result += '</dd>'

        return result


    def formatvalue(self, object):
        """Format an argument default value as text."""
        return '<span class="parameter-default">=%s</span>' % self.repr(object)


    def docroutine(self, object, name=None, mod=None,
                   funcs={}, classes={}, methods={}, cl=None):
        """Produce HTML documentation for a function or method object."""
        realname = object.__name__
        name = name or realname
        anchor = (cl and cl.__name__ or '') + '-' + name
        note = ''
        skipdocs = 0

        if inspect.ismethod(object):
            imclass = object.im_class
            if cl:
                if imclass is not cl:
                    note = ' from ' + self.classlink(imclass, mod)
            else:
                if object.im_self is not None:
                    note = ' method of %s instance' % self.classlink(
                        object.im_self.__class__, mod)
                else:
                    note = ' unbound %s method' % self.classlink(imclass,mod)
            object = object.im_func

        if name == realname:
            title = '<a name="%s" href="#%s"><span class="function-name">%s</span></a>' % (anchor, anchor, realname)
        else:
            if (cl and realname in cl.__dict__ and
                cl.__dict__[realname] is object):
                reallink = '<a href="#%s">%s</a>' % (
                    cl.__name__ + '-' + realname, realname)
                skipdocs = 1
            else:
                reallink = realname
            title = '<a name="%s" href="#%s"><span class="function-name">%s</span></a> = %s' % (
                anchor, anchor, name, reallink)

        if inspect.isfunction(object):
            args, varargs, varkw, defaults = inspect.getargspec(object)
            argspec = inspect.formatargspec(
                args, varargs, varkw, defaults, formatvalue=self.formatvalue)
            if realname == '<lambda>':
                title = '<span class="function-name lambda">%s</span> <em>lambda</em> ' % name
                argspec = argspec[1:-1] # remove parentheses
        else:
            argspec = '(...)'

        argspec = '<span class="argspec">%s</span>' % argspec
        decl = title + argspec + (note and '<span class="note">%s</span>' % note)

        if skipdocs:
            return '<dl><dt>%s</dt></dl>\n' % decl
        else:
            doc = self.markup(
                self.getdoc(object), self.preformat, funcs, classes, methods)
            doc = doc and '<dd>%s</dd>' % doc
            return '<dl class="function"><dt>%s</dt>%s</dl>\n' % (decl, doc)


    def _docdescriptor(self, name, value, mod):
        results = []
        push = results.append

        push('<dl class="descriptor">')
        if name:
            push('<dt>%s</dt>\n' % name)
        if value.__doc__ is not None:
            doc = self.getdoc(value)
            push('<dd>%s</dd>\n' % doc)
        push('</dl>\n')

        return ''.join(results)

    def docproperty(self, object, name=None, mod=None, cl=None):
        """Produce html documentation for a property."""
        return self._docdescriptor(name, object, mod)

    def docother(self, object, name=None, mod=None, *ignored):
        """Produce HTML documentation for a data object."""
        lhs = name and '<span class="other-name">%s</span> = ' % name or '' # fucking what?
        return lhs + self.repr(object)

    def docdata(self, object, name=None, mod=None, cl=None):
        """Produce html documentation for a data descriptor."""
        return self._docdescriptor(name, object, mod)


@app.expose('/doc/')
class Documentation(poobrains.auth.Protected):

    """
    A `Renderable` that can created and render module documentation on the fly.
    """

    handle = None
    title = None
    text = None

    def __init__(self, handle=None, **kwargs):

        super(Documentation, self).__init__(**kwargs)

        self.handle = handle
        md_path = os.path.join(app.poobrain_path, 'doc', '%s.md' % handle)

        if handle is None:
            import __main__
            doc = PooDoc()
            subject = __main__
            text = doc.document(subject)

        elif os.path.exists(md_path):

            self.title = handle.title()
            self.text = poobrains.md.MarkdownString(codecs.open(md_path, 'r', encoding='utf-8').read())

        elif sys.modules.has_key(handle):
            
            doc = PooDoc()
            subject = sys.modules[handle]
            self.title = subject.__name__
            self.text = poobrains.rendering.RenderString(jinja2.Markup(doc.document(subject)))

        else:
            raise poobrains.errors.ExposedError("Whoops.")


    def view(self, mode='full', **kwargs):

        r = Response(super(Documentation, self).view(mode=mode, **kwargs))
        r.cache_control.public = True
        r.cache_control.max_age = app.config['CACHE_LONG']

        return r
