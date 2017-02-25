from setuptools import setup, find_packages

setup(
    name='poobrains',
    author='phryk',
    install_requires=['flask', 'peewee', 'pyspkac', 'pyScss'],
    packages=['poobrains'],
    #packages=find_packages(),
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
    ]
)
