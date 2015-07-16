# -*- coding: utf-8 -*-
from setuptools import setup
setup(
    name='dist1',
    version='0.1',
    description="A dummy distribution",
    long_description=u"Long description.\n\nGruß.\n",
    classifiers=[
        "Topic :: Software Development :: Testing",
        ],
    author='Jeff Dairiki',
    author_email='dairiki@dairiki.org',
    keywords='dummy testing',
    py_modules=['dist1'],
    install_requires=[],
    scripts=[
        'dist1_script',
        ],
    entry_points={
        'console_scripts': [
            'dist1_wrapper = dist1:main',
            ],
        },
    extras_require={
        'extras': ['extension_dist'],
        },
    )
