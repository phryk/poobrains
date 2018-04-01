import os
import shutil
import unittest

import poobrains
from click.testing import CliRunner

class FakeHTTPSMiddleware(object):

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):

        environ['wsgi.url_scheme'] = 'https'
        environ['SSL_CLIENT_VERIFY'] = 'FNORD'
        return self.app(environ, start_response)


class PooTest(unittest.TestCase):

    @classmethod
    def setUpClass(self):

        poobrains.app.wsgi_app = FakeHTTPSMiddleware(poobrains.app.wsgi_app)
        poobrains.app.testing = True
        self.client = poobrains.app.test_client()

    @classmethod
    def tearDownClass(cls):

        try:
            shutil.rmtree(os.path.join(poobrains.app.site_path, 'gnupg'))
        except:
            pass

        try:
            os.unlink('config.py')
        except:
            pass

        try:
            os.unlink('example.db')
        except:
            pass

        try:
            os.unlink('example.ini')
        except:
            pass

        try:
            os.unlink('example.nginx.conf')
        except:
            pass

    def test_cli_install(self):

        input = """poobrains.local



poobrains@mail.local
mail.local
587
poobrains
poopass
root@mail.local



y
"""
        if not os.environ.has_key('FLASK_APP'):
            os.environ['FLASK_APP'] = '__main__'
        runner = CliRunner()
        rv = runner.invoke(poobrains.cli.install, input=input)
        print rv.output

        assert not rv.exception, rv.exception.message
        assert "Installation complete!" in rv.output, "Installation apparently didn't complete!"

#    def test_redeem_token(self):
#
#        challenge_request = self.client.get('/cert')
#        print challenge_request.data


def run_all():

    runner = unittest.runner.TextTestRunner(failfast=False)
    suite = unittest.TestLoader().loadTestsFromTestCase(PooTest)
    runner.run(suite)
