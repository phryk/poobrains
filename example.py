#!/usr/bin/env python

import flask
import poobrains

from flask import redirect
#from poobrains import Poobrain, poobrains.storage.Storable, poobrains.rendering.Menu, Renderable
#from peewee import poobrains.storage.fields.CharField, poobrains.storage.fields.TextField
#from poobrains.storage.fields import poobrains.storage.fields.CharField, poobrains.storage.fields.TextField

app = poobrains.app

@app.route('/')
def front():
    return redirect(News.url())


@app.site.route('/form', methods=['GET', 'POST'])
@poobrains.rendering.render()
def form_test():

    form = TestForm()

    if flask.request.method == 'POST':
        form.handle(flask.request.form)
        return poobrains.rendering.RenderString("ZOMGPOST")

    return form 

class TestSubForm(poobrains.form.Fieldset):

    oink = poobrains.form.fields.Text(label="OMGWTF")
    foo = poobrains.form.fields.Text(label="SUBfoo")
    submit = poobrains.form.Button('submit', label="SUBSUBMIT") 


class TestForm(poobrains.form.Form):

    foo = poobrains.form.fields.Text()
    bar = TestSubForm()
    trigger = poobrains.form.Button('submit', label='Hit me!')


@app.expose('/news')
class News(poobrains.storage.Storable):

    text = poobrains.storage.fields.TextField()


@app.expose('/paste', title='Copypasta')
class Paste(poobrains.storage.Storable):

    type = poobrains.storage.fields.CharField()
    text = poobrains.storage.fields.TextField()


@app.site.box('menu_main')
def menu_main():

    menu = poobrains.rendering.Menu('main')
    menu.append(News.url(), 'News')
    menu.append(Paste.url(), 'Pastes')

    return menu


class NonExposed(poobrains.storage.Storable):

    text = poobrains.storage.fields.TextField()


class NonExposedB(NonExposed):
    pass


@app.site.listing(NonExposedB, '/custom', mode='full', title='Custom Listing')
def list_nonexposed(listing):

    return listing


if __name__ == '__main__':

    app.run()
