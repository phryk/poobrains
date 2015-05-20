from peewee import CharField
from poobrains import Poobrain, BaseModel, Storable, Menu, view

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


@app.box('menu-main')
def menu_main():
    menu = Menu('main')
    menu.append('foo', 'Foo')
    menu.append('bar', 'Bar')

    return menu


if __name__ == '__main__':

    app.run()
