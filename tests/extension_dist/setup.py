# -*- coding: utf-8 -*-
from setuptools import setup, Extension
setup(
    name='extension_dist',
    version='0.1',
    description="A dummy distribution",
    long_description="A distribution with an extension module.",
    classifiers=[
        "Topic :: Software Development :: Testing",
        ],
    author='Jeff Dairiki',
    author_email='dairiki@dairiki.org',
    keywords='dummy testing',
    packages=['extension_dist'],
    ext_modules=[
        Extension('extension_dist.test_ext', ['test_ext.c']),
        ],
    eager_resources=[
        'extension_dist/answer.dat',
        ],
    package_data={
        'extension_dist': ['*.dat'],
        },
    entry_points={
        'console_scripts': [
            'get_answer_from_ext = extension_dist:main',
            'read_answer_from_data = extension_dist:answer_from_resource',
            ],
        },
    )
