# -*- coding: utf-8 -*-
"""
The documentation system.
"""

import os
import re
import sys
import string
import codecs # needed to open files with utf-8 encoding
import inspect
import pkgutil
import pydoc
import jinja2

from poobrains import app
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

#    def docroutine(self, object, name=None, mod=None,
#                   funcs={}, classes={}, methods={}, cl=None):
#        """Produce HTML documentation for a function or method object."""
#
#        app.debugger.set_trace()
#        return "blargh"

    # some utility functions first

    level_offset = None
    local = None
    index_url = None

    def __init__(self, level_offset=0, local=False, index_url='/doc/'): 

        self.level_offset = level_offset
        self.local = local
        self.index_url = index_url


    def heading(self, level, content):

        """ Create a HTML heading """

        level += self.level_offset
        if level > 6:
            level = 6 # HTML headings only go from h1 to h6

        return "<h%d>%s</h%d>" % (level, content, level)
    
    
    def url(self, name):

        """ Create URL for a documentable thing. Mainly intended for subclassing """

        return "/doc/%s" % name

    
    def listing(self, items, formatter=None):

        if formatter is not None:
            items = ['<li>' + formatter(item) + '</li>' for item in items]
        return '<ul class="list">%s</ul>' % ''.join(items) # <ul> might not be semantically correct, <ol> a better choice?


    def preformat(self, text):

        return '<pre>%s</pre>' % text


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



    def formattree(self, tree, modname, parent=None):

        """Render in text a class tree as returned by inspect.getclasstree()."""

        result = '<ul class="tree">'
        for entry in tree:
            result += '<li>'
            if type(entry) is type(()): # means this is info about a class
                c, bases = entry
                result += '<span class="classname">' + pydoc.classname(c, modname) + '</span>'

                if bases and bases != (parent,):
                    parents = map(lambda c, m=modname: pydoc.classname(c, m), bases)
                    result +=  '(<span class="bases">%s</span>)' % ', '.join(parents)

            elif type(entry) is type([]): # means this is a list of child classes of the previous item
                result += self.formattree(entry, modname, c)

            result += '</li>'

        result += '</ul>'
        app.debugger.set_trace()

        return result


    def markup(self, text, escape=None, funcs={}, classes={}, methods={}):

        """Mark up some plain text, given a context of symbols to look for.
        Each context dictionary maps object names to anchor names."""


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


        components['doc'] = poobrains.md.md.convert(self.markup(pydoc.getdoc(object), funcs=fdict, classes=cdict)) # build documentation for the thing passed in


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

            components['classes'] = self.heading(level + 2, 'Classes') + classtree + '\n'.join(classdocs)

        
        if funcs:

            docs = []
            for key, value in funcs:
                docs.append('<div class="function">' + self.document(value, key, name, fdict, cdict) + '</div>')
            components['funcs'] = self.heading(level + 2, 'Functions') + '\n'.join(docs)


        if data:

            docs = []
            for key, value in data:
                docs.append('<div class="data">' + self.document(value, key))

            components['data'] = self.heading(level + 2, 'Data') + '\n'.join(docs)



        if hasattr(object, '__author__'):

            components['author'] = self.heading(level + 2, 'Author') + pydoc._binstr(object.__author__)


        if hasattr(object, '__credits__'):

            components['credits'] = self.geadubg(level + 2, 'Credits') + pydoc._binstr(object.__credits__)


        app.debugger.set_trace()


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
        realname = object.__name__
        name = name or realname
        bases = object.__bases__

        return "dem class shit"




class DocMD(pydoc.Doc):

    """ 
    200% doc

    A pydoc.Doc subclass that outputs documentation as markdown.

    """

    _repr_instance = MDRepr()
    repr = _repr_instance.repr

    def header(self, text, level=2): # default level is 2 because we're assuming this to be integrated in some page that already has a h1 title

        pad = '#' * level
        return u"%s %s %s" % (pad, text, pad)

    def bold(self, text):
        """Format a string in bold by cuddling it in **."""
        return u"**%s**" % text

    def indent(self, text, prefix='    '):
        """Indent text by prepending a given prefix to each line."""
        if not text: return ''
        lines = string.split(text, '\n')
        lines = map(lambda line, prefix=prefix: prefix + line, lines)
        if lines: lines[-1] = string.rstrip(lines[-1])
        return string.join(lines, '\n')


    def listing(self, items):
        return u"\n" + u"\n* ".join(items)


    def section(self, title, contents):
        """Format a section with a given heading."""
        return self.header(title) + '\n\n' + string.rstrip(contents) + '\n\n\n'

    # ---------------------------------------------- type-specific routines

    def formattree(self, tree, modname, parent=None, prefix=''):
        """Render in text a class tree as returned by inspect.getclasstree()."""
        result = ''
        for entry in tree:
            if type(entry) is type(()):
                c, bases = entry
                result = result + prefix + '* ' + pydoc.classname(c, modname)
                if bases and bases != (parent,):
                    parents = map(lambda c, m=modname: pydoc.classname(c, m), bases)
                    result = result + '(%s)' % string.join(parents, ', ')
                result = result + '\n'
            elif type(entry) is type([]):
                result = result + self.formattree(
                    entry, modname, c, prefix + '    ')
        return result

    def docmodule(self, object, name=None, mod=None):
        """Produce text documentation for a given module object."""
        name = object.__name__ # ignore the passed-in name
        synop, desc = pydoc.splitdoc(getdoc(object))
        result = self.section('NAME', name + (synop and ' - ' + synop))

        try:
            all = object.__all__
        except AttributeError:
            all = None

        try:
            file = inspect.getabsfile(object)
        except TypeError:
            file = '(built-in)'
        result = result + self.section('FILE', file)

        docloc = self.getdocloc(object)
        if docloc is not None:
            result = result + self.section('MODULE DOCS', docloc)

        if desc:
            result = result + self.section('DESCRIPTION', desc)

        classes = []
        for key, value in inspect.getmembers(object, inspect.isclass):
            # if __all__ exists, believe it.  Otherwise use old heuristic.
            if (all is not None
                or (inspect.getmodule(value) or object) is object):
                if pydoc.visiblename(key, all, object):
                    classes.append((key, value))
        funcs = []
        for key, value in inspect.getmembers(object, inspect.isroutine):
            # if __all__ exists, believe it.  Otherwise use old heuristic.
            if (all is not None or
                inspect.isbuiltin(value) or inspect.getmodule(value) is object):
                if pydoc.visiblename(key, all, object):
                    funcs.append((key, value))
        data = []
        for key, value in inspect.getmembers(object, pydoc.isdata):
            if pydoc.visiblename(key, all, object):
                data.append((key, value))

        modpkgs = []
        modpkgs_names = set()
        if hasattr(object, '__path__'):
            for importer, modname, ispkg in pkgutil.iter_modules(object.__path__):
                modpkgs_names.add(modname)
                if ispkg:
                    modpkgs.append(modname + ' (package)')
                else:
                    modpkgs.append(modname)

            modpkgs.sort()
            result = result + self.section(
                'PACKAGE CONTENTS', string.join(modpkgs, '\n'))

        # Detect submodules as sometimes created by C extensions
        submodules = []
        for key, value in inspect.getmembers(object, inspect.ismodule):
            if value.__name__.startswith(name + '.') and key not in modpkgs_names:
                submodules.append(key)
        if submodules:
            submodules.sort()
            result = result + self.section(
                'SUBMODULES', string.join(submodules, '\n'))

        if classes:
            classlist = map(lambda key_value: key_value[1], classes)
            contents = [self.formattree(
                inspect.getclasstree(classlist, 1), name)]
            for key, value in classes:
                contents.append(self.document(value, key, name))
            result = result + self.section('CLASSES', string.join(contents, '\n'))

        if funcs:
            contents = []
            for key, value in funcs:
                contents.append(self.document(value, key, name))
            result = result + self.section('FUNCTIONS', string.join(contents, '\n'))

        if data:
            contents = []
            for key, value in data:
                contents.append(self.docother(value, key, name, maxlen=70))
            result = result + self.section('DATA', string.join(contents, '\n'))

        if hasattr(object, '__version__'):
            version = pydoc._binstr(object.__version__)
            if version[:11] == '$' + 'Revision: ' and version[-1:] == '$':
                version = strip(version[11:-1])
            result = result + self.section('VERSION', version)
        if hasattr(object, '__date__'):
            result = result + self.section('DATE', pydoc._binstr(object.__date__))
        if hasattr(object, '__author__'):
            result = result + self.section('AUTHOR', pydoc._binstr(object.__author__))
        if hasattr(object, '__credits__'):
            result = result + self.section('CREDITS', pydoc._binstr(object.__credits__))
        #return clean(result)
        return result

    def docclass(self, object, name=None, mod=None, *ignored):
        """Produce text documentation for a given class object."""
        
        realname = object.__name__
        name = name or realname
        bases = object.__bases__

        def makename(c, m=object.__module__):
            return pydoc.classname(c, m)

        if name == realname:
            title = 'class ' + self.bold(realname)
        else:
            title = self.bold(name) + ' = class ' + realname
        if bases:
            parents = map(makename, bases)
            title = title + '(%s)' % string.join(parents, ', ')

        doc = getdoc(object)
        contents = doc and [doc + '\n'] or []
        push = contents.append

        # List the mro, if non-trivial.
        mro = pydoc.deque(inspect.getmro(object))
        if len(mro) > 2:
            push("Method resolution order:")
            for base in mro:
                push('\n* ' + makename(base))
            push('')

        # Cute little class to pump out a horizontal rule between sections.
        class HorizontalRule:
            def __init__(self):
                self.needone = 0
            def maybe(self):
                if self.needone:
                    push('-' * 70)
                self.needone = 1
        hr = HorizontalRule()

        def spill(msg, attrs, predicate):
            ok, attrs = pydoc._split_list(attrs, predicate)
            if ok:
                hr.maybe()
                push(msg)
                for name, kind, homecls, value in ok:
                    try:
                        value = getattr(object, name)
                    except Exception:
                        # Some descriptors may meet a failure in their __get__.
                        # (bug #1785)
                        push(self._docdescriptor(name, value, mod))
                    else:
                        push(self.document(value,
                                        name, mod, object))
            return attrs

        def spilldescriptors(msg, attrs, predicate):
            ok, attrs = pydoc._split_list(attrs, predicate)
            if ok:
                hr.maybe()
                push(msg)
                for name, kind, homecls, value in ok:
                    push(self._docdescriptor(name, value, mod))
            return attrs

        def spilldata(msg, attrs, predicate):
            ok, attrs = pydoc._split_list(attrs, predicate)
            if ok:
                hr.maybe()
                push(msg)
                for name, kind, homecls, value in ok:
                    if (hasattr(value, '__call__') or
                            inspect.isdatadescriptor(value)):
                        doc = getdoc(value)
                    else:
                        doc = None
                    push(self.docother(getattr(object, name),
                                       name, mod, maxlen=70, doc=doc) + '\n')
            return attrs

        attrs = filter(lambda data: pydoc.visiblename(data[0], obj=object),
                       pydoc.classify_class_attrs(object))
        while attrs:
            if mro:
                thisclass = mro.popleft()
            else:
                thisclass = attrs[0][2]
            attrs, inherited = pydoc._split_list(attrs, lambda t: t[2] is thisclass)

            if thisclass is pydoc.__builtin__.object:
                attrs = inherited
                continue
            elif thisclass is object:
                tag = "defined here"
            else:
                tag = "inherited from %s" % pydoc.classname(thisclass,
                                                      object.__module__)

            # Sort attrs by name.
            attrs.sort()

            # Pump out the attrs, segregated by kind.
            attrs = spill("Methods %s:\n" % tag, attrs,
                          lambda t: t[1] == 'method')
            attrs = spill("Class methods %s:\n" % tag, attrs,
                          lambda t: t[1] == 'class method')
            attrs = spill("Static methods %s:\n" % tag, attrs,
                          lambda t: t[1] == 'static method')
            attrs = spilldescriptors("Data descriptors %s:\n" % tag, attrs,
                                     lambda t: t[1] == 'data descriptor')
            attrs = spilldata("Data and other attributes %s:\n" % tag, attrs,
                              lambda t: t[1] == 'data')
            assert attrs == []
            attrs = inherited

        contents = '\n'.join(contents)
        if not contents:
            return title + '\n'
        return clean(title + '\n\n' + string.rstrip(contents) + '\n\n\n')

    def formatvalue(self, object):
        """Format an argument default value as text."""
        return '=' + self.repr(object)

    def docroutine(self, object, name=None, mod=None, cl=None):
        """Produce text documentation for a function or method object."""
        realname = object.__name__
        name = name or realname
        note = ''
        skipdocs = 0
        if inspect.ismethod(object):
            imclass = object.im_class
            if cl:
                if imclass is not cl:
                    note = ' from ' + pydoc.classname(imclass, mod)
            else:
                if object.im_self is not None:
                    note = ' method of %s instance' % pydoc.classname(
                        object.im_self.__class__, mod)
                else:
                    note = ' unbound %s method' % pydoc.classname(imclass,mod)
            object = object.im_func

        if name == realname:
            title = self.bold(realname)
        else:
            if (cl and realname in cl.__dict__ and
                cl.__dict__[realname] is object):
                skipdocs = 1
            title = self.bold(name) + ' = ' + realname
        if inspect.isfunction(object):
            args, varargs, varkw, defaults = inspect.getargspec(object)
            argspec = inspect.formatargspec(
                args, varargs, varkw, defaults, formatvalue=self.formatvalue)
            if realname == '<lambda>':
                title = self.bold(name) + ' lambda '
                argspec = argspec[1:-1] # remove parentheses
        else:
            argspec = '(...)'
        decl = title + argspec + note

        if skipdocs:
            return decl + '\n'
        else:
            doc = getdoc(object) or ''
            return decl + '\n' + (doc and string.rstrip(self.indent(doc)) + '\n')

    def _docdescriptor(self, name, value, mod):
        results = []
        push = results.append

        if name:
            push(self.bold(name))
            push('\n')
        doc = getdoc(value) or ''
        if doc:
            push(self.indent(doc))
            push('\n')
        return ''.join(results)

    def docproperty(self, object, name=None, mod=None, cl=None):
        """Produce text documentation for a property."""
        return self._docdescriptor(name, object, mod)

    def docdata(self, object, name=None, mod=None, cl=None):
        """Produce text documentation for a data descriptor."""
        return self._docdescriptor(name, object, mod)

    def docother(self, object, name=None, mod=None, parent=None, maxlen=None, doc=None):
        """Produce text documentation for a data object."""
        repr = self.repr(object)
        if maxlen:
            line = (name and name + ' = ' or '') + repr
            chop = maxlen - len(line)
            if chop < 0: repr = repr[:chop] + '...'
        line = (name and self.bold(name) + ' = ' or '') + repr
        if doc is not None:
            line += '\n' + self.indent(unicode(doc))
        return line


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
            doc = DocMD()
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
