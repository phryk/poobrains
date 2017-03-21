# -*- coding: utf-8 -*-

import peewee
import flask
import poobrains 


class SearchField(poobrains.form.fields.Text):
    pass


@poobrains.app.site.box('search')
class SearchForm(poobrains.form.Form):

    pattern = SearchField()
    search = poobrains.form.Button('submit', value='search', label='Search')

    def __init__(self, *args, **kwargs):

        if not kwargs.has_key('action'):
            kwargs['action'] = poobrains.app.site.get_view_url(Search, '', 'full')

        if not self.fields['pattern'].value and flask.session.has_key('search_pattern'):
            self.fields['pattern'].value = flask.session['search_pattern']

        super(SearchForm, self).__init__(*args, **kwargs)


@poobrains.app.expose('/search/', mode='full')
class Search(poobrains.auth.Protected):

    form = None
    handle = None
    results = None

    def __init__(self, handle=''):
        
        super(Search, self).__init__(name=self.__class__.__name__)

        self.handle = handle

        self.form = SearchForm()
        self.form.fields['pattern'].value = self.handle
        self.form.clear = poobrains.form.Button('submit', value='clear', label='Clear')
        self.results = []


    @poobrains.helpers.themed
    def view(self, mode='full', *args, **kwargs):

        if flask.request.method == 'POST':
            
            pattern = flask.request.form[self.form.name]['pattern']

            if flask.request.form.has_key('clear'):
                flask.session.pop('search_pattern', None)
                return flask.redirect(poobrains.app.site.get_view_url(self.__class__, '', 'full'))

            self.handle = pattern
            flask.session['search_pattern'] = pattern
            return flask.redirect(self.url('full'))

        if len(self.handle) == 0 and flask.session.has_key('search_pattern'):
            if len(flask.session['search_pattern']) >= 3:
                # redirect requests with empty search handle to the saved search
                self.handle = flask.session['search_pattern']
                return flask.redirect(self.url('full'))

        administerables = poobrains.auth.Administerable.children_keyed()
        readable_administerables = []

        if len(self.handle) >= 3:

            flask.session['search_pattern'] = self.handle

            for key in sorted(administerables):

                administerable = administerables[key]

                try:
                    administerable.permissions['read'].check(flask.g.user)
                    readable_administerables.append(administerable)

                except poobrains.auth.PermissionDenied:
                    pass

            for administerable in readable_administerables:

                q = administerable.list('r', flask.g.user).limit(poobrains.app.config['PAGINATION_COUNT'])
                clauses = []

                term = '*%s*' % self.handle
                if isinstance(getattr(administerable, 'title', None), poobrains.storage.fields.CharField):
                    clauses.append((peewee.fn.Lower(administerable.title) % term)) # LIKE clause

                if isinstance(getattr(administerable, 'name', None), poobrains.storage.fields.CharField):
                    clauses.append((peewee.fn.Lower(administerable.name) % term))

                if len(clauses):
                    q = q.where(reduce(peewee.operator.or_, clauses))
                else:
                    continue

                for result in q:
                    if len(self.results) >= 10:
                        break

                    self.results.append(result)

        elif len(self.handle) > 0:
            flask.flash("Search pattern has to be at least 3 characters long.", 'error')

#        elif flask.session.has_key('search_pattern') and 

        return self
