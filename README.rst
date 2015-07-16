======================================
Humpty - Convert Python wheels to eggs
======================================

|version| |build status|

For when you need an ``.egg`` but all you have is a ``.whl``.

***********
Description
***********

Humpty is a command-line utility to convert Python binary wheel
packages to eggs.

Currently, the tool is in a “works for me” state.  (It is not
guaranteed to work for you.)

Development takes place on github_.

.. _github: https://github.com/dairiki/humpty/

********
Synopsis
********

The humpty "man page"::

  $ humpty --help
  Usage: humpty [OPTIONS] WHEELS...

    Convert wheels to eggs.

  Options:
    -d, --dist-dir DIR  Build eggs into <dir>.  Default is <cwd>/dist.
    --help              Show this message and exit.

Suppose you need an egg of a distribution which has only been uploaded
to PyPI as a wheel::

  $ pip install --download . publicsuffixlist
  [...]
    Saved ./publicsuffixlist-0.2.8-py2.py3-none-any.whl
  Successfully downloaded publicsuffixlist

  $ humpty -dist-dir . publicsuffixlist-0.2.8-py2.py3-none-any.whl
  Converting publicsuffixlist-0.2.8-py2.py3-none-any.whl to publicsuffixlist-0.2.8-py2.6.egg

  $ easy_install publicsuffixlist-0.2.8-py2.7.egg


**********
References
**********

- :PEP:`427` - The Wheel Binary Package Format 1.0
- :PEP:`491` - The Wheel Binary Package Format 1.9
- :PEP:`241` - Metadata for Python Software Packages
- :PEP:`314` - Metadata for Python Software Packages v1.1
- :PEP:`345` - Metadata for Python Software Packages 1.2
- :PEP:`426` - Metadata for Python Software Packages 2.0
- :PEP:`459` - Standard Metadata Extensions for Python Software Packages
- Setuptools: `The Internal Structure of Python Eggs`_

.. _the internal structure of python eggs:
   http://pythonhosted.org/setuptools/formats.html


*******
Authors
*******

`Jeff Dairiki`_

.. _Jeff Dairiki: mailto:dairiki@dairiki.org

.. |version| image::
    https://img.shields.io/pypi/v/humpty.svg
    :target: https://pypi.python.org/pypi/humpty/
    :alt: Latest Version

.. |build status| image::
    https://travis-ci.org/dairiki/humpty.svg?branch=master
    :target: https://travis-ci.org/dairiki/humpty
