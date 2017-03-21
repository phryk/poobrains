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
            kwargs['action'] = poobrains.app.site.get_view_url(Search, '', 'full')

        if not self.fields['pattern'].value and flask.session.has_key('search_pattern'):
            self.fields['pattern'].value = flask.session['search_pattern']

        super(SearchForm, self).__init__(*args, **kwargs)


@poobrains.app.expose('/search/', mode='full')
class Search(poobrains.auth.Protected):

    form = None
    handle = None
    offset = 0
    results = None

    def __init__(self, handle='', offset=0):
        
        super(Search, self).__init__(name=self.__class__.__name__)

        self.handle = handle

        self.form = SearchForm()
        self.form.fields['pattern'].value = self.handle
        self.form.clear = poobrains.form.Button('submit', value='clear', label='Clear')
        self.offset = offset
        self.results = []


    def pagination_info(self, limit, offset, counts):

        position = 0
        info = collections.OrderedDict()

        range_lower = offset
        range_upper = offset + limit - 1

        for administerable, count in counts.iteritems():

            if count > 0:

                first_position = position
                last_position = first_position + count - 1

                on_current_page = first_position <= range_upper and last_position >= range_lower

                if on_current_page:
                
                    info[administerable] = {}

                    starts_before_page = first_position < range_lower
                    starts_within_page = first_position >= range_lower and first_position <= range_upper
                    ends_after_page = last_position > range_upper

                    if starts_before_page:
                        info[administerable]['offset'] = range_lower - first_position
                    else:
                        info[administerable]['offset'] = 0

                    if starts_within_page and ends_after_page:
                        info[administerable]['limit'] = limit - (first_position - range_lower)
                    else:
                        info[administerable]['limit'] = limit

                position += count# + 1

        return info




    @poobrains.helpers.themed
    def view(self, mode='full', offset=0, **kwargs):

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

                except poobrains.auth.AccessDenied:
                    pass

            queries = collections.OrderedDict()
            for administerable in readable_administerables:

                q = administerable.list('r', flask.g.user)
                clauses = []

                term = '*%s*' % self.handle.lower()

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
                    queries[administerable] = q.where(reduce(peewee.operator.or_, clauses))
                else:
                    continue

            counts = collections.OrderedDict()

            total_results = 0
            for administerable, query in queries.iteritems():
                c = query.count()
                counts[administerable] = c
                total_results += c
            
            pagination_info = self.pagination_info(poobrains.app.config['PAGINATION_COUNT'], offset, counts)

            for administerable, info in pagination_info.iteritems():

                query = queries[administerable]

                query = query.offset(info['offset'])
                query = query.limit(info['limit'])

                for result in query:
                    self.results.append(result)

            num_pages = int(math.ceil(float(total_results) / poobrains.app.config['PAGINATION_COUNT']))

            if num_pages > 1:

                self.pagination = poobrains.rendering.Menu('menu-pagination')
                current_page = int(offset / poobrains.app.config['PAGINATION_COUNT']) + 1

                for i in range(0, num_pages):
       
                    page_num = i + 1
                    active = page_num == current_page

                    self.pagination.append(
                        flask.url_for('site.search_handle_offset', handle=self.handle, offset=i * poobrains.app.config['PAGINATION_COUNT']),
                        page_num,
                        active
                    )
                    
            else:
                self.pagination = False


        elif len(self.handle) > 0:
            flask.flash("Search pattern has to be at least 3 characters long.", 'error')


        return self


poobrains.app.site.add_view(Search, '/search/', mode='full', endpoint='search')
poobrains.app.site.add_view(Search, '/search/<handle>/', mode='full', endpoint='search_handle')
poobrains.app.site.add_view(Search, '/search/<handle>/+<int:offset>', mode='full', endpoint='search_handle_offset')
