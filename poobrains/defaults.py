# -*- coding: utf-8 -*-

from . import md_default

DOMAIN = 'localhost'
SITE_NAME = 'poobrains'
LOGFILE = False # examples: 'poobrains.log', '/var/log/poobrains.log' TODO: is this really needed with nginx logging?
THEME = 'default'
PAGINATION_COUNT = 10

TOKEN_VALIDITY = 600
MAX_TOKENS = 5 # maximum number of allowed clientcert tokens for a single user
CERT_LIFETIME = 60 * 60 * 24 * 7 # TODO: Shouldn't this be user-selectable at time of certificate provisioning?

SVG_PLOT_WIDTH = 540 # width of svg plots (the plot itself, not the overall svg
SVG_PLOT_HEIGHT = 290 # height of svg plots
SVG_PLOT_PADDING = 40 # padding around an svg plot
SVG_PLOT_DESCRIPTION_HEIGHT = 300 # height for dataset descriptions

# NOTE/WARNING: if you change svg map dimensions, you will fuck up coordinates unless you generate a fitting themes/default/svg/world.jinja!
SVG_MAP_WIDTH = 620
SVG_MAP_HEIGHT = 618
SVG_MAP_INFOBOX_WIDTH = 200
SVG_MAP_INFOBOX_HEIGHT = 200

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
