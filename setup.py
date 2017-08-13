from setuptools import setup, find_packages

setup(
    name='poobrains',
    author='phryk',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Programming Language :: Python :: 2.7',
    ],
    install_requires=[
        'flask',
        'peewee',
        'pyspkac',
        'pyOpenSSL', # because apparently this is marked neither by pyspkac nor by m2crypto as dependency…
        'pyScss',
        'pillow',
        'markdown',
        'gnupg'],
    extras_require={
        'dev': ['pudb'], 
    },
    packages=find_packages(),
    include_package_data=True,
)
