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
    optin = poobrains.form.fields.Checkbox(label="Opt-in", default=None, required=True)
    trigger = poobrains.form.Button('submit', label='Hit me!')

    def handle(self):
        flask.flash('TestForm.handle called!')
        return self


@app.expose('/news', mode='full')
class News(poobrains.auth.NamedOwned):

    title = poobrains.storage.fields.CharField()
    text = poobrains.storage.fields.TextField()


@app.expose('/paste', mode='full', title='Copypasta')
class Paste(poobrains.auth.Owned):

    type = poobrains.storage.fields.CharField()
    text = poobrains.storage.fields.TextField()


@app.site.box('menu_main')
def menu_main():

    menu = poobrains.rendering.Menu('main')
    menu.append(News.url(), 'News')
    menu.append(Paste.url(), 'Pastes')

    return menu


class NonExposed(poobrains.auth.Administerable):

    text = poobrains.storage.fields.TextField()


class NonExposedB(NonExposed):
    pass


@app.site.listing(NonExposedB, '/custom', mode='full', title='Custom Listing')
def list_nonexposed(listing):

    return listing


if __name__ == '__main__':

    app.run()
