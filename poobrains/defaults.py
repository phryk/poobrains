# -*- coding: utf-8 -*-

from . import md_default

DOMAIN = 'localhost'
SITE_NAME = 'poobrains'
DATABASE = 'sqlite:///poobrains.db' # database url, containing password, if any. at least sqlite and postres should be supported
LOGFILE = False # examples: 'poobrains.log', '/var/log/poobrains.log' TODO: is this really needed with nginx logging?
THEME = 'default'
PAGINATION_COUNT = 10

TOKEN_VALIDITY = 600
MAX_TOKENS = 5 # maximum number of allowed clientcert tokens for a single user
CERT_LIFETIME = 60 * 60 * 24 * 7 # TODO: Shouldn't this be user-selectable at time of certificate provisioning?

SMTP_HOST = None # str, ip address or dns name
SMTP_PORT = 587 # int
SMTP_STARTTLS = True
SMTP_ACCOUNT = None # str
SMTP_PASSWORD = None # str
SMTP_FROM = None

CRYPTO_KEYLENGTH = 4096

GPG_BINARY = None
GPG_HOME = None # str, path
GPG_SIGNKEY = None # str, a gpg key fingerprint
GPG_PASSPHRASE = None # str, gpg key passphrase for signing

CACHE_SHORT = 60 * 15 # 15 minutes
CACHE_LONG = 60 * 60 * 24 * 7 # a week

MARKDOWN_CLASS = md_default.pooMarkdown
MARKDOWN_EXTENSIONS = ['markdown.extensions.codehilite', 'markdown.extensions.fenced_code', 'markdown.extensions.tables']
MARKDOWN_OUTPUT = 'html5'
