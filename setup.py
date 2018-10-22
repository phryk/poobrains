from setuptools import setup, find_packages

setup(
    name='poobrains',
    author='phryk',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        #'Programming Language :: Python :: 2.7',
    ],
    install_requires=[
        'flask',
        'peewee',
        'pyOpenSSL', # to create TLS client certs
        'pyScss',
        'pillow',
        'markdown',
        'pretty-bad-protocol'], # formerly 'gnupg'
    extras_require={
        'dev': ['pudb'], 
    },
    packages=find_packages(),
    include_package_data=True,
)
