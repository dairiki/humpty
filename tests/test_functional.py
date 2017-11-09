# -*- coding: utf-8 -*-
"""
"""
from __future__ import absolute_import

from contextlib import contextmanager
import imp
import posixpath
from zipfile import ZipFile

from click.testing import CliRunner
import pkginfo
import pytest
from six import PY3


def test_pyfile_compiled(packages, tmpdir):
    packages.require_eggs('dist1')
    unzip = False
    if PY3:
        # Python >= 3.2 doesn't seem to run .pyc files from PEP 3147
        # (__pycache__) repository directories.
        unzip = True
    venv = packages.get_venv('dist1', unzip=unzip)
    assert venv.run("__import__('dist1').test_is_compiled()") == 0


@pytest.fixture
def dist1_metadata(packages):
    egg = packages.get_egg('dist1')
    return pkginfo.BDist(str(egg))


def test_summary(dist1_metadata):
    assert dist1_metadata.summary == "A dummy distribution"


def test_description(dist1_metadata):
    assert dist1_metadata.description.rstrip() \
        == u"Long description.\n\nGruß."


def test_script_wrapper(packages):
    packages.require_eggs('dist1')
    venv = packages.get_venv('dist1')
    assert venv.call(['dist1_wrapper']) == 42


def test_old_style_script(packages):
    packages.require_eggs('dist1')
    venv = packages.get_venv('dist1')
    assert venv.call(['dist1_script']) == 42


def test_namespace_package(packages):
    packages.require_eggs('dist1', 'dist2')
    venv = packages.get_venv('dist2')
    prog = (
        'import sys\n'
        'from dist2.plugins.builtin import the_answer\n'
        'sys.exit(the_answer)\n'
        )
    assert venv.run(prog) == 42


def test_namespace_stubs_in_egg(packages):
    dist2_egg = packages.get_egg('dist2')
    dist2_stubs = with_byte_compiled(['dist2/__init__.py',
                                      'dist2/plugins/__init__.py'])
    with fileobj(ZipFile(str(dist2_egg))) as zf:
        files_in_egg = dist2_stubs.intersection(zf.namelist())

    # Make sure we generated the stubs (or not, depending on python
    # version)
    stubs_in_egg = files_in_egg.intersection(dist2_stubs)
    assert stubs_in_egg == dist2_stubs

    # Make sure we didn't copy the .pth file that the wheel installer
    # creates for the namespaces
    assert not any(fn.lower().endswith('.pth')
                   for fn in files_in_egg)


def test_extension(packages):
    packages.require_eggs('extension_dist')
    venv = packages.get_venv('extension_dist')
    assert venv.run("__import__('extension_dist').test_extension()") == 0


def test_eager_resources(packages):
    packages.require_eggs('extension_dist')
    venv = packages.get_venv('extension_dist')
    assert venv.run("__import__('extension_dist').test_eager_resources()") == 0


def test_extras(packages):
    packages.require_eggs('dist1', 'extension_dist')
    venv = packages.get_venv('dist1[extras]')
    assert venv.run("__import__('dist1').test_extras()") == 0


def test_no_extras(packages):
    packages.require_eggs('dist1', 'extension_dist')
    venv = packages.get_venv('dist1')
    assert venv.run("__import__('dist1').test_no_extras()") == 0


def test_main(packages, tmpdir):
    from humpty import main

    wheel = packages.get_wheel('dist1')

    runner = CliRunner()
    result = runner.invoke(main, ['-d', str(tmpdir), str(wheel)])
    assert result.exit_code == 0

    eggs = list(tmpdir.listdir(fil="*.egg"))
    assert len(eggs) == 1
    egg = eggs[0]
    assert egg.isfile()
    assert egg.fnmatch("dist1-*")


@contextmanager
def fileobj(fp):
    try:
        yield fp
    finally:
        fp.close()


def with_byte_compiled(paths):
    """ Augment PATHS with paths of byte-compiled files.
    """
    get_tag = getattr(imp, 'get_tag', None)
    compiled = set()
    for path in paths:
        head, tail = posixpath.split(path)
        root, ext = posixpath.splitext(tail)
        if ext == '.py':
            if get_tag:
                root = '%s.%s' % (root, get_tag())
                head = posixpath.join(head, '__pycache__')
            compiled.add(posixpath.join(head, root + '.pyc'))
    return compiled.union(paths)
