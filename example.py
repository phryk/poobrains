#!/usr/bin/env python

import flask
import poobrains

from flask import redirect


app = poobrains.app

@app.route('/')
def front():
    return redirect(News.url())


class TestSubForm(poobrains.form.Fieldset):

    oink = poobrains.form.fields.Text(label="OMGWTF")
    foo = poobrains.form.fields.Text(label="SUBfoo")
    submit = poobrains.form.Button('submit', label="SUBSUBMIT") 


@app.expose('/form')
class TestForm(poobrains.form.Form):

    foo = poobrains.form.fields.Text()
    bar = TestSubForm()
    optin = poobrains.form.fields.Checkbox(label="Opt-in", default=False, required=True, choices=[(True, None)])
    completeme = poobrains.form.fields.Text(label="Lookit me, I can autocomplete without JS!", choices=[('Mr. Foo', 'foo'), ('Mr. Florb', 'florb'), ('Ms. Bar', 'bar')])
    trigger = poobrains.form.Button('submit', label='Hit me!')

    def process(self):
        flask.flash('TestForm.process called!')
        return self


@app.expose('/news', mode='full')
class News(poobrains.commenting.Commentable):

    """ This is the news class docstring """

    class Meta:
        search_fields = ['title', 'name', 'text']

    title = poobrains.storage.fields.CharField()
    text = poobrains.md.MarkdownField()


@app.expose('/paste', mode='full', title='Copypasta')
class Paste(poobrains.tagging.Taggable):

    type = poobrains.storage.fields.CharField()
    text = poobrains.storage.fields.TextField()


@app.site.box('menu_main')
def menu_main():

    menu = poobrains.rendering.Menu('main')

    try:
        News.permissions['read'].check(flask.g.user)
        menu.append(News.url(), 'News')
    except poobrains.auth.AccessDenied:
        pass
    
    try:
        Paste.permissions['read'].check(flask.g.user)
        menu.append(Paste.url(), 'Pastes')
    except poobrains.auth.AccessDenied:
        pass

    return menu


class NonExposed(poobrains.auth.Administerable):

    text = poobrains.storage.fields.TextField()


class NonExposedB(NonExposed):
    pass

class AVeryVeryLongNameToTestMenuPositioning(poobrains.auth.Administerable):
    pass

#class MultiPK(poobrains.auth.Administerable):
#
#    class Meta:
#        primary_key = peewee.CompositeKey('pk_a', 'pk_b')
#
#    pk_a = poobrains.storage.fields.IntegerField()
#    pk_b = poobrains.storage.fields.IntegerField()
#
#
#class NestedHandle(poobrains.auth.Administerable):
#
#    class Meta:
#        primary_key = peewee.CompositeKey('foreign', 'local')
#
#    foreign = poobrains.storage.fields.ForeignKeyField(MultiPK)
#    local = poobrains.storage.fields.CharField()


@app.site.listing(NonExposedB, '/custom', mode='full', title='Custom Listing')
def list_nonexposed(listing):

    return listing


if __name__ == '__main__':

    #app.run()
    poobrains.app.cli()
