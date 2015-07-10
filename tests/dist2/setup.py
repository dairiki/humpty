# -*- coding: utf-8 -*-
from setuptools import setup, find_packages
setup(
    name='dist2',
    version='0.2',
    description="Another dummy distribution",
    long_description="Long description.",
    classifiers=[
        "Topic :: Software Development :: Testing",
        ],
    author='Jeff Dairiki',
    author_email='dairiki@dairiki.org',
    keywords='dummy testing',
    packages=find_packages(),
    namespace_packages=['dist2', 'dist2.plugins'],
    install_requires=['dist1'],
    )
