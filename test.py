from peewee import CharField
from flask import url_for
from poobrains import Poobrain, BaseModel, Storable, Menu, Listing, view

print __name__, __file__

app = Poobrain('Poobrains')

class TestA(Storable):
    test = CharField()

class TestB(Storable):
    pass

class TestB1(TestB):
    pass


@app.site.route('/testa/<id_or_name>')
@view
def testa_load(id_or_name):

    return TestA.load(id_or_name)


@app.site.route('/lista/')
@app.site.route('/lista/<int:offset>/')
#@app.site.listroute('/lista/')
@view
def testa_list(offset=0):

    return Listing(TestA, offset)


@app.site.listroute('/listb/')
@view
def testb_list(offset=0):

    return Listing(TestB, offset)


@app.site.box('menu-main')
def menu_main():

    print "MENU_MAIN"
    menu = Menu('main')
    menu.append(url_for('site.testa_list'), 'TestA')
    menu.append(url_for('site.testb_list'), 'TestB')

    return menu


if __name__ == '__main__':

    print app.view_functions

    app.run()
