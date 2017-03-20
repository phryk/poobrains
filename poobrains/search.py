# -*- coding: utf-8 -*-

import peewee
import flask
import poobrains 


class SearchField(poobrains.form.fields.Text):
    pass


class SearchForm(poobrains.form.Form):

    norz = 'schnorz'
    pattern = SearchField()
    search = poobrains.form.Button('submit', value='search', label='Search')
    clear = poobrains.form.Button('submit', value='clear', label='Clear')
    orz = 'schnorz'


@poobrains.app.expose('/search/', mode='full')
class Search(poobrains.rendering.Renderable):

    form = None
    handle = None
    results = None

    def __init__(self, handle=''):

        super(Search, self).__init__(name=self.__class__.__name__)

        self.handle = handle
        if handle == '' and flask.session.has_key('search_pattern'):
            self.handle = session['search_pattern']

        self.form = SearchForm()
        self.form.pattern.value = self.handle
        self.form.action = poobrains.app.site.get_view_url(self.__class__, '', 'full')
        self.results = []


    @poobrains.helpers.themed
    def view(self, mode='full', *args, **kwargs):

        if flask.request.method == 'POST':
            
            pattern = flask.request.form[self.form.name]['pattern']

            if flask.request.form.has_key('clear'):
                flask.session.pop('search_pattern', None)
                return flask.redirect(self.url('full'))

            self.handle = pattern
            return flask.redirect(self.url('full'))

        administerables = poobrains.auth.Administerable.children_keyed()
        readable_administerables = []

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

        return self
