# -*- coding: utf-8 -*-
"""
"""
from __future__ import absolute_import

from contextlib import contextmanager
import imp
import posixpath
import re
from subprocess import call, check_call
import sys
from zipfile import ZipFile

from click.testing import CliRunner
import pkginfo
import py
import pytest
from six import PY3


@pytest.fixture(scope='session')
def session_tmpdir(request):
    tmpdir_handler = getattr(request.config, '_tmpdirhandler', None)
    if tmpdir_handler:
        # Create session tmpdir within pytest's session tmpdir
        # Include '.' in name to avoid name clashes with the stock tmpdir.
        return tmpdir_handler.mktemp('session.dir', numbered=False)
    else:                       # pragma: NO COVER
        return py.path.local.make_numbered_dir('humpty-')


@pytest.fixture(scope='session')
def packages(session_tmpdir):
    return PackageManager(session_tmpdir)


def test_pyfile_compiled(packages, tmpdir):
    packages.require_eggs('dist1')
    venv = packages.get_venv('dist1', unzip=PY3)
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


class PackageManager(object):
    def __init__(self, tmpdir):
        self.tmpdir = tmpdir
        self.wheelhouse = tmpdir.join('wheelhouse')
        self.distdir = tmpdir.join('dist')
        self.wheels = {}
        self.eggs = {}
        self.venvs = {}

    def get_wheel(self, dist_name):
        wheel = self.wheels.get(dist_name)
        if wheel is None:
            tmpdir = py.path.local.make_numbered_dir('tmp', self.tmpdir)
            wheel = build_wheel(dist_name, self.wheelhouse, tmpdir)
            self.wheels[dist_name] = wheel
        return wheel

    def get_egg(self, dist_name):
        egg = self.eggs.get(dist_name)
        if egg is None:
            wheel = self.get_wheel(dist_name)
            egg = build_egg(wheel, self.distdir)
            self.eggs[dist_name] = egg
        return egg

    def require_eggs(self, *dists):
        for dist in dists:
            self.get_egg(dist)

    def get_venv(self, *dists, **kwargs):
        dists = frozenset(dists)
        unzip = kwargs.get('unzip', False)
        venv = self.venvs.get(dists)
        if venv is None:
            name = '-'.join(sorted(re.sub(r'\W', '_', dist) for dist in dists))
            if unzip:
                name += '-unzipped'
            vdir = self.tmpdir.join("venv_%s" % name)
            venv = Virtualenv(vdir, self.distdir, install=dists, unzip=unzip)
            self.venvs[dists] = venv
        return venv


def build_wheel(dist_name, wheelhouse, tmpdir):
    srcdir = py.path.local(__file__).dirpath(dist_name)
    setup_py = [sys.executable, 'setup.py']

    # Put all the build artifacts in our own private tmpdirs
    # so that simultaneous tox runs don't overwite each others builds
    ourtmp = tmpdir.ensure_dir(dist_name)
    setup_py.extend(['egg_info',
                     '--egg-base', str(ourtmp)])
    setup_py.extend(['build',
                     '--build-base', str(ourtmp.join('build')),
                     '--build-temp', str(ourtmp.join('btmp'))])

    print("==== Building wheel for %s ====" % dist_name)
    with srcdir.as_cwd():
        check_call(setup_py + ['bdist_wheel', '--dist-dir', str(wheelhouse)])

    wheels = wheelhouse.listdir(
        lambda f: f.isfile() and f.fnmatch("%s-*.whl" % dist_name))
    assert len(wheels) <= 1, "found too many wheels"
    return wheels[0]


def build_egg(wheel, egg_dir):
    from humpty import main

    name_ver = '-'.join(wheel.basename.split('-')[:2])
    match = lambda p: p.fnmatch("%s-*" % name_ver)
    existing_eggs = set()
    if egg_dir.exists():
        existing_eggs.update(egg_dir.listdir(fil=match))

    print("==== Building egg from %s ====" % wheel)
    runner = CliRunner()
    result = runner.invoke(main, ['-d', str(egg_dir), str(wheel)])
    assert result.exit_code == 0

    new_eggs = set(egg_dir.listdir(fil=match)).difference(existing_eggs)
    egg = new_eggs.pop()
    assert len(new_eggs) == 0
    return egg


class Virtualenv(object):
    def __init__(self, path, find_links=None, install=None, unzip=False):
        self.path = py.path.local(path)
        self.environ = {'PATH': str(self.path.join('bin'))}
        print("==== Creating virtualenv at %s ====" % path)
        check_call([sys.executable, '-m', 'virtualenv',
                    '--no-site', str(path)])

        if install:
            cmd = ['easy_install', '--index-url', 'file:///dev/null']
            if find_links:
                cmd.extend(['--find-links', str(find_links)])
            if unzip or True:
                cmd.append('--always-unzip')
            cmd.extend(install)
            self.check_call(cmd)

        # Make virtualenv read-only
        for p in path.visit(fil="*.egg"):
            if p.isdir():
                p.chmod(0o500)

    def call(self, cmd, **kwargs):
        kwargs['env'] = self.environ
        return call(cmd, **kwargs)

    def check_call(self, cmd, **kwargs):
        kwargs['env'] = self.environ
        check_call(cmd, **kwargs)

    def run(self, prog, **kwargs):
        return self.call(['python', '-c', prog], **kwargs)

    def check_run(self, prog, **kwargs):
        return self.check_call(['python', '-c', prog], **kwargs)


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
