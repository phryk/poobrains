from setuptools import setup, find_packages

setup(
    name='poobrains',
    author='phryk',
    install_requires=['flask', 'peewee', 'pyspkac', 'pyScss'],
    extras_require={
        'dev': ['pudb'], 
    },
    packages=find_packages(),
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Programming Language :: Python :: 2.7',
    ]
)
