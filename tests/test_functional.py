# -*- coding: utf-8 -*-
"""
"""
from __future__ import absolute_import

from subprocess import call, check_call
import sys

import pkginfo
import py
import pytest


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

    with srcdir.as_cwd():
        check_call(setup_py + ['bdist_wheel', '--dist-dir', str(wheelhouse)])

    wheels = wheelhouse.listdir(
        lambda f: f.isfile() and f.fnmatch("%s-*.whl" % dist_name))
    assert len(wheels) <= 1, "found too many wheels"
    return wheels[0]


def build_egg(wheel, egg_dir):
    from humpty import EggWriter
    return EggWriter(str(wheel)).build_egg(str(egg_dir))


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
def wheelhouse(session_tmpdir):
    return session_tmpdir.join('wheelhouse')


@pytest.fixture(scope='session')
def distdir(session_tmpdir):
    return session_tmpdir.join('dist')


@pytest.fixture(scope='session')
def dist1_whl(wheelhouse, session_tmpdir):
    return build_wheel('dist1', wheelhouse, session_tmpdir)


@pytest.fixture(scope='session')
def dist2_whl(wheelhouse, session_tmpdir):
    return build_wheel('dist2', wheelhouse, session_tmpdir)


@pytest.fixture(scope='session')
def dist1_egg(dist1_whl, distdir):
    return build_egg(dist1_whl, distdir)


@pytest.fixture(scope='session')
def dist2_egg(dist2_whl, distdir):
    return build_egg(dist2_whl, distdir)


@pytest.fixture
def dist1_metadata(dist1_egg):
    return pkginfo.BDist(dist1_egg)


@pytest.fixture
def dist2_metadata(dist2_egg):
    return pkginfo.BDist(dist2_egg)


@pytest.fixture(scope='session')
def dist1_venv(distdir, dist1_egg, session_tmpdir):
    venv_dir = session_tmpdir.join('dist1_venv')
    venv = Virtualenv(str(venv_dir))

    print("DISTDIR '%s'" % distdir)

    venv.check_call([
        'easy_install',
        '--find-links', str(distdir),
        '--index-url', 'file:///dev/null',
        'dist1'])
    return venv


@pytest.fixture(scope='session')
def dist2_venv(distdir, dist1_egg, dist2_egg, session_tmpdir):
    venv_dir = session_tmpdir.join('dist2_venv')
    venv = Virtualenv(str(venv_dir))
    venv.check_call([
        'easy_install',
        '--find-links', ' '.join([dist1_egg, dist2_egg]),
        '--index-url', 'file:///dev/null',
        'dist2'])
    return venv


class Virtualenv(object):
    def __init__(self, path):
        self.path = py.path.local(path)
        self.environ = {'PATH': str(self.path.join('bin'))}
        check_call(['virtualenv', '--no-site', path])

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


def test_pyfile_compiled(dist1_venv, tmpdir):
    stdout = tmpdir.join('stdout')
    dist1_venv.check_run(
        "import dist1; print(getattr(dist1, '__cached__', dist1.__file__))",
        stdout=stdout.open('w'))
    assert stdout.read_text('utf-8').strip().endswith('.pyc')


def test_summary(dist1_metadata):
    assert dist1_metadata.summary == "A dummy distribution"


@pytest.mark.xfail
def test_description(dist1_metadata):
    assert dist1_metadata.description == "Long description"


def test_script_wrapper(dist1_venv):
    assert dist1_venv.call(['script_wrapper']) == 42


def test_old_style_script(dist1_venv):
    assert dist1_venv.call(['old_style_script']) == 42


def test_namespace_package(dist2_venv):
    prog = (
        'import sys\n'
        'from dist2.plugins.builtin import the_answer\n'
        'sys.exit(the_answer)\n'
        )
    assert dist2_venv.run(prog) == 42
