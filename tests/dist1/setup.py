# -*- coding: utf-8 -*-
from setuptools import setup
setup(
    name='dist1',
    version='0.1',
    description="A dummy distribution",
    long_description="Long description.",
    classifiers=[
        "Topic :: Software Development :: Testing",
        ],
    author='Jeff Dairiki',
    author_email='dairiki@dairiki.org',
    keywords='dummy testing',
    py_modules=['dist1'],
    install_requires=[],
    scripts=[
        'old_style_script',
        ],
    entry_points={
        'console_scripts': [
            'script_wrapper = dist1:main',
            ],
        },
    )
