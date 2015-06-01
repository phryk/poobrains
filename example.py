from peewee import CharField, TextField
from flask import redirect
from poobrains import Poobrain, Storable, Menu

app = Poobrain('Poobrains Example')


@app.site.route('/')
def front():
    return redirect(News.url())


@app.site.expose('/news')
class News(Storable):

    text = TextField()


@app.site.expose('/paste')
class Paste(Storable):

    type = CharField()
    text = TextField()


@app.box('menu-main')
def menu_main():

    menu = Menu('main')
    menu.append(News.url(), 'News')
    menu.append(Paste.url(), 'Pastes')

    return menu


if __name__ == '__main__':

    app.run()
