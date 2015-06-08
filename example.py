from peewee import CharField, TextField
from flask import redirect
from poobrains import Poobrain, Storable, Menu, Renderable

app = Poobrain('Poobrains Example')


@app.route('/')
def front():
    return redirect(News.url())


@app.expose('/news')
class News(Storable):

    text = TextField()


@app.expose('/paste', title='Copypasta')
class Paste(Storable):

    type = CharField()
    text = TextField()


@app.box('menu-main')
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
