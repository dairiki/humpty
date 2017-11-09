# -*- coding: utf-8 -*-
import os
import sys

from setuptools import setup
from setuptools.command.test import test as TestCommand

VERSION = '0.1.post1.dev0'

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()
CHANGES = open(os.path.join(here, 'CHANGES.rst')).read()

requires = [
    'click',
    'distlib',
    'setuptools',
    'six',
    ]

tests_require = [
    'pytest',
    'pytest-catchlog',
    'pkginfo',
    'virtualenv',
    ]


class PyTest(TestCommand):
    user_options = [('pytest-args=', 'a', "Arguments to pass to py.test")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = []

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # import here, cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main(self.pytest_args)
        sys.exit(errno)

cmdclass = {'test': PyTest}

setup(
    name='humpty',
    version=VERSION,
    description="A tool to convert python wheels to eggs",
    long_description=README + '\n\n' + CHANGES,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python",
        "Topic :: System :: Archiving :: Packaging",
        "Topic :: System :: Software Distribution",
        ],
    author='Jeff Dairiki',
    author_email='dairiki@dairiki.org',
    url='https://github.com/dairiki/humpty',
    keywords='python packaging wheel whl egg',

    py_modules=['humpty'],
    install_requires=requires,

    include_package_data=True,
    zip_safe=True,

    entry_points={
        'console_scripts': [
            'humpty = humpty:main',
            ],
        },

    tests_require=tests_require,
    cmdclass=cmdclass,
    extras_require={
        "testing": tests_require,
        },
    )
