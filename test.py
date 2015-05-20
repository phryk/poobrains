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


@app.route('/testa/<id_or_name>')
@view
def testa_load(id_or_name):

    return TestA.load(id_or_name)


#@app.route('/lista/')
#@app.route('/lista/<int:offset>/')
@app.listroute('/lista/')
@view
def testa_list(offset=0):

    return Listing(TestA, offset)


@app.listroute('/listb')
@view
def testb_list(offset=0):

    return Listing(TestB, offset)


@app.box('menu-main')
def menu_main():
    menu = Menu('main')
    menu.append(url_for('testa_list'), 'TestA')
    menu.append(url_for('testb_list'), 'TestB')

    return menu


if __name__ == '__main__':

    app.run()
