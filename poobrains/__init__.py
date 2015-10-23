#from pkgutil import extend_path
#__path__ = extend_path(__path__, __name__)

import rendering
import cli
import storage
import auth
from poobrains import Poobrain
from rendering import Renderable, Menu, render
from storage import Model, Storable, Listing

app = Poobrain(__name__)
