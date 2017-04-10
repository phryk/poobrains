# -*- coding: utf-8 -*-

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication

import smtplib
import gnupg

import flask
import poobrains

def getgpg():
    return gnupg.GPG(homedir=poobrains.app.config['GPG_HOME'])


class MailError(Exception):
    pass


class Mail(MIMEMultipart):

    fingerprint = None
    crypto = None

    def __init__(self, fingerprint=None, **kwargs):

        MIMEMultipart.__init__(self, **kwargs)
        self.fingerprint = fingerprint
        self.crypto = getgpg()
        self['From'] = poobrains.app.config['SMTP_FROM']


    def as_string(self, unixfrom=False):

        fingerprint = str(self.fingerprint) # TODO: enforce str by implementing __setattr__?

        wrapper_msg = MIMEMultipart(_subtype='encrypted', protocol='application/pgp-encrypted')
        wrapper_msg['To'] = self['To']
        wrapper_msg['Subject'] = self['Subject']

        pgp_info = MIMEApplication(b"Version: 1\n", _subtype='pgp-encrypted', _encoder=lambda x: str(x))
        pgp_info['Content-Disposition'] = 'attachment'
        wrapper_msg.attach(pgp_info)

        self_string = MIMEMultipart.as_string(self, unixfrom=unixfrom)

        crypto_kw = {
            'symmetric': False # IIUC symmetric=True makes us at risk for leaking private keys
        }

        if  poobrains.app.config['GPG_PASSPHRASE'] is not None and \
            poobrains.app.config['GPG_SIGNKEY'] is not None:
                crypto_kw['passphrase'] = poobrains.app.config['GPG_PASSPHRASE']
                crypto_kw['default_key'] = poobrains.app.config['GPG_SIGNKEY']

        ciphertext = str(self.crypto.encrypt(self_string, str(self.fingerprint), **crypto_kw))
        if ciphertext != '':
            pgp_attachment = MIMEApplication(ciphertext, _encoder=lambda x: str(x))#, _subtype='octet-stream')
            wrapper_msg.attach(pgp_attachment)

            return wrapper_msg.as_string(unixfrom=unixfrom)


        if hasattr(cryptinfo.stderr):
            poobrains.app.logger.error("Problem encrypting mail. stderr follows.")
            poobrains.app.logger.error(cryptinfo.stderr)
        else:
            poobrains.app.logger.error("Problem encrypting mail. No further information.")

        raise MailError("Problem encrypting mail.")


    def send(self):

        if not isinstance(self.fingerprint, basestring):
            raise MailError('Trying to send mail without selecting public key fingerprint.')

        if self['To'] is None:
            raise MailError('Recipient for mail not set!')

        if poobrains.app.config['SMTP_STARTTLS']:
            smtp = smtplib.SMTP(poobrains.app.config['SMTP_HOST'], port=poobrains.app.config['SMTP_PORT'])
            smtp.starttls() # FIXME: We'll want to check if this actually worked

        else:
            smtp = smtplib.SMTP_SSL(poobrains.app.config['SMTP_HOST'], port=poobrains.app.config['SMTP_PORT'])

        smtp.ehlo()
        smtp.login(poobrains.app.config['SMTP_ACCOUNT'], poobrains.app.config['SMTP_PASSWORD'])
        smtp.sendmail(self['From'], self['To'], self.as_string())


#@poobrains.app.site.route('/testmail')
#def testmail():
#
#    user = poobrains.auth.User.load('administrator')
#
#    mail = Mail()
#    mail['To'] = user.mail
#    mail.fingerprint = user.pgp_fingerprint
#    mail['Subject'] = 'Testmail'
#    mail.attach(MIMEText(u'Jurbn Schnörbn\nFlörb'.encode('utf-8'), 'plain', 'utf-8'))
#    
#    fd = open('upload/image/poobrains.gif', 'rb')
#    attachment = MIMEImage(fd.read()) 
#    fd.close()
#
#    mail.attach(attachment)
#
#    mail.send()
#
#    return "Florb sent?"
