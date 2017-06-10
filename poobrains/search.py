# -*- coding: utf-8 -*-

import collections
import math
import peewee
import flask

import poobrains 


class SearchField(poobrains.form.fields.Text):
    pass


@poobrains.app.box('search')
def box_search():
    try:
        Search.permissions['read'].check(flask.g.user)
        return SearchForm()
    except poobrains.auth.AccessDenied:
        return None


class SearchForm(poobrains.form.Form):

    pattern = SearchField()
    search = poobrains.form.Button('submit', value='search', label='Search')

    def __init__(self, *args, **kwargs):

        if not kwargs.has_key('action'):
            kwargs['action'] = poobrains.app.site.get_view_url(Search, mode='full')

        if not self.fields['pattern'].value and flask.session.has_key('search_pattern'):
            self.fields['pattern'].value = flask.session['search_pattern']

        super(SearchForm, self).__init__(*args, **kwargs)


class Search(poobrains.auth.Protected):

    form = None
    handle = None
    offset = None
    results = None

    def __init__(self, handle='', offset=0, **kwargs):
        
        super(Search, self).__init__(name=self.__class__.__name__)

        self.handle = handle

        self.form = SearchForm()
        self.form.fields['pattern'].value = self.handle
        self.form.clear = poobrains.form.Button('submit', value='clear', label='Clear')
        self.offset = offset
        self.results = []


    @poobrains.helpers.themed
    def view(self, mode='full', offset=0, **kwargs):

        if flask.request.method == 'POST':
            
            pattern = flask.request.form[self.form.name]['pattern']

            if flask.request.form.has_key('clear'):
                flask.session.pop('search_pattern', None)
                return flask.redirect(poobrains.app.site.get_view_url(self.__class__, mode='full'))

            self.handle = pattern
            flask.session['search_pattern'] = pattern
            return flask.redirect(self.url('full'))

        if len(self.handle) == 0 and flask.session.has_key('search_pattern'):
            if len(flask.session['search_pattern']) >= 3:
                # redirect requests with empty search handle to the saved search
                self.handle = flask.session['search_pattern']
                return flask.redirect(self.url('full'))

        administerables = poobrains.auth.Administerable.class_children_keyed()
        readable_administerables = []

        if len(self.handle) >= 3:

            flask.session['search_pattern'] = self.handle

            for key in sorted(administerables):

                administerable = administerables[key]

                try:
                    administerable.permissions['read'].check(flask.g.user)
                    readable_administerables.append(administerable)

                except poobrains.auth.AccessDenied:
                    pass

            queries = []
            
            for administerable in readable_administerables:

                q = administerable.list('read', flask.g.user)
                clauses = []

                term = '%%%s%%' % self.handle.lower()

                if hasattr(administerable._meta, 'search_fields'):

                    for field_name in administerable._meta.search_fields:

                        field = getattr(administerable, field_name)
                        clauses.append((peewee.fn.Lower(field) % term))

                else:
                    
                    if isinstance(getattr(administerable, 'name', None), poobrains.storage.fields.CharField):
                        clauses.append((peewee.fn.Lower(administerable.name) % term))

                    if isinstance(getattr(administerable, 'title', None), poobrains.storage.fields.CharField):
                        clauses.append((peewee.fn.Lower(administerable.title) % term)) # LIKE clause
                    
                    if isinstance(getattr(administerable, 'text', None), poobrains.storage.fields.TextField):
                        clauses.append((peewee.fn.Lower(administerable.text) % term)) # LIKE clause

                if len(clauses):
                    queries.append(q.where(reduce(peewee.operator.or_, clauses)))
                else:
                    continue


            pagination = poobrains.storage.Pagination(queries, offset, 'site.search_handle_offset', handle=self.handle)
            self.results = pagination.results
            self.pagination = pagination.menu


        elif len(self.handle) > 0:
            flask.flash(u"Search pattern has to be at least 3 characters long.", 'error')

        return self


poobrains.app.site.add_view(Search, '/search/', mode='full', endpoint='search')
poobrains.app.site.add_view(Search, '/search/<handle>/', mode='full', endpoint='search_handle')
poobrains.app.site.add_view(Search, '/search/<handle>/+<int:offset>', mode='full', endpoint='search_handle_offset')
