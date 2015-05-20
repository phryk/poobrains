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


if __name__ == '__main__':

    main_menu = Menu('main')
    main_menu.append('foo', 'Foo')
    main_menu.append('bar', 'Bar')

    app.add_menu(main_menu)
    
    app.run()
