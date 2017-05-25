from setuptools import setup, find_packages

setup(
    name='poobrains',
    author='phryk',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Programming Language :: Python :: 2.7',
    ],
    install_requires=['flask', 'peewee', 'pyspkac', 'pyScss', 'pillow', 'markdown'],
    extras_require={
        'dev': ['pudb'], 
    },
    packages=find_packages(),
    include_package_data=True,
)
