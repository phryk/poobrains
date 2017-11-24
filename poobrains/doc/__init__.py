import string
import inspect
import pkgutil
import pydoc

from poobrains import app
import poobrains.helpers
import poobrains.storage
import poobrains.auth
import poobrains.md


def clean(text):

    return text.replace('<', '&lt;').replace('>', '&gt;')


def getdoc(obj):

    return clean(pydoc.getdoc(obj))


class MDRepr(pydoc.TextRepr):

    def repr_string(self, x, level):
        app.debugger.set_trace()
        return clean(super(MDRepr, self).repr_string(x, level))

    def reor1(self, x, level):
        app.debugger.set_trace()


class DocMD(pydoc.Doc):

    """ 200% doc """

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
        app.debugger.set_trace()
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
            version = _binstr(object.__version__)
            if version[:11] == '$' + 'Revision: ' and version[-1:] == '$':
                version = strip(version[11:-1])
            result = result + self.section('VERSION', version)
        if hasattr(object, '__date__'):
            result = result + self.section('DATE', _binstr(object.__date__))
        if hasattr(object, '__author__'):
            result = result + self.section('AUTHOR', _binstr(object.__author__))
        if hasattr(object, '__credits__'):
            result = result + self.section('CREDITS', _binstr(object.__credits__))
        return clean(result)

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


@app.route('/doctest')
@poobrains.helpers.themed
def doctest():

    doc = DocMD()
    return poobrains.md.MarkdownString(doc.document(poobrains.storage.Storable))


@app.expose('/doc/')
class Documentation(poobrains.auth.Protected):


    handle = None
    title = None
    text = None

    def __init__(self, handle=None, **kwargs):


        super(Documentation, self).__init__(**kwargs)

        doc = DocMD()

        self.handle = handle

        addr = handle.split('.')
        
        if handle is None:
            import __main__
            subject = getattr(__main__)

        elif addr[0] == 'poobrains':

            if len(addr) == 1:
                subject = poobrains

            else:
                subject = getattr(poobrains, addr[1])

        else:
            import __main__
            subject = getattr(__main__, addr[0])

        self.title = subject.__name__
        self.text = poobrains.md.MarkdownString(doc.document(subject))
