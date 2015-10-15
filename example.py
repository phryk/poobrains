#!/usr/bin/env python

import flask
import poobrains

from flask import redirect
from poobrains import Poobrain, Storable, Menu, Renderable
#from peewee import CharField, TextField
from poobrains.storage.fields import CharField, TextField

app = Poobrain('Poobrains Example')


@app.route('/')
def front():
    return redirect(News.url())


@app.site.route('/form', methods=['GET', 'POST'])
@poobrains.rendering.render()
def form_test():

    if flask.request.method == 'POST':
        flask.current_app.logger.debug(flask.request.method)
        flask.current_app.logger.debug(flask.request.form.getlist('foo'))
        return poobrains.rendering.RenderString("ZOMGPOST")

    return TestForm()


class TestSubForm(poobrains.form.Fieldset):

    oink = poobrains.form.fields.Text(label="OMGWTF")
    foo = poobrains.form.fields.Text(label="SUBfoo")
    submit = poobrains.form.Button('submit', label="SUBSUBMIT") 


class TestForm(poobrains.form.Form):

    foo = poobrains.form.fields.Text()
    bar = TestSubForm()
    trigger = poobrains.form.Button('submit', label='Hit me!')


@app.expose('/news')
class News(Storable):

    text = TextField()


@app.expose('/paste', title='Copypasta')
class Paste(Storable):

    type = CharField()
    text = TextField()


@app.site.box('menu_main')
def menu_main():

    menu = Menu('main')
    menu.append(News.url(), 'News')
    menu.append(Paste.url(), 'Pastes')

    return menu


class NonExposed(Storable):

    text = TextField()


class NonExposedB(NonExposed):
    pass


@app.site.listing(NonExposedB, '/custom', mode='full', title='Custom Listing')
def list_nonexposed(listing):

    return listing


if __name__ == '__main__':

    app.run()
