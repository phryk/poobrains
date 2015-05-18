from peewee import CharField
from projectname import ProjectName, BaseModel, Storable, Menu, view

app = ProjectName('ProjectName')

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
