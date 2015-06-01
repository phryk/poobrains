from peewee import CharField
from flask import url_for
from poobrains import Poobrain, BaseModel, Storable, Menu, Listing, render

app = Poobrain('Poobrains')

@app.site.expose('/testa')
class TestA(Storable):
    test = CharField()

class TestB(Storable):
    
    def __call__(self, *args, **kw):
        print "TestB called w/: ", args
        print kw

        return "dem wat"

class TestB1(TestB):
    pass


@app.site.expose('/x/')
class TestX(Storable):
    pass

#@app.site.route('/testa/<id_or_name>')
#@render
#def testa_load(id_or_name):
#
#    return TestA.load(id_or_name)

@app.site.view(TestA, '/oinks/', primary=True)
def wtf(instance):
    print "DEM INSTANCE: ", instance

    return instance

#@app.site.route('/lista/')
#@app.site.route('/lista/<int:offset>/')
#@app.site.listing(TestA, '/lista/')
#def testa_list(instance):

#    return instance


#@app.site.listing(TestB, '/listb/')
#def testb_list(instance):
#
#    return instance


@app.box('menu-main')
def menu_main():

    menu = Menu('main')
    menu.append(TestA.url(), 'TestA')
#    menu.append(url_for('site.testb_list'), 'TestB')

    return menu


app.site.add_listing(TestA, '/barf/')
app.site.add_view(TestX, '/barf/')
app.site.add_view(TestX, '/barf42/')


if __name__ == '__main__':

    app.run()
