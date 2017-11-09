# -*- coding: utf-8 -*-
"""
"""
from __future__ import absolute_import

import re
from subprocess import call, check_call
import sys

import py
import pytest


@pytest.fixture(scope='session')
def session_tmpdir(request):
    tmpdir_handler = getattr(request.config, '_tmpdirhandler', None)
    if tmpdir_handler:
        # Create session tmpdir within pytest's session tmpdir
        return tmpdir_handler.mktemp('session', numbered=False)
    else:                       # pragma: NO COVER
        return py.path.local.make_numbered_dir('humpty-')


@pytest.fixture(scope='session')
def packages(session_tmpdir, request):
    return PackageManager(session_tmpdir, request)


class PackageManager(object):
    def __init__(self, tmpdir, request):
        self.tmpdir = tmpdir
        self.wheelhouse = tmpdir.join('wheelhouse')
        self.distdir = tmpdir.join('dist')
        self.wheels = {}
        self.eggs = {}
        self.venvs = {}
        self.saved_modes = []
        # restore modes so that pytest can delete the tmpdir
        request.addfinalizer(self._restore_modes)

    def _restore_modes(self):
        while self.saved_modes:
            path, mode = self.saved_modes.pop()
            path.chmod(mode)

    def get_wheel(self, dist_name, python_tag=None):
        key = dist_name, python_tag
        wheel = self.wheels.get(key)
        if wheel is None or True:
            tmpdir = py.path.local.make_numbered_dir('tmp', self.tmpdir)
            wheel = build_wheel(dist_name, self.wheelhouse, tmpdir,
                                python_tag=python_tag)
            self.wheels[key] = wheel
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

            # Make installed eggs read-only
            for p in vdir.visit(fil="*.egg"):
                if p.isdir():
                    self.saved_modes.append((p, p.stat().mode))
                    p.chmod(0o500)

        return venv


def build_wheel(dist_name, wheelhouse, tmpdir, python_tag=None):
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

    bdist_wheel = ['bdist_wheel', '--dist-dir', str(ourtmp)]
    if python_tag is not None:
        bdist_wheel.extend(['--python-tag', python_tag])

    print("==== Building wheel for %s ====" % dist_name)
    with srcdir.as_cwd():
        check_call(setup_py + bdist_wheel)

    new_wheels = ourtmp.listdir(lambda f: f.isfile()
                                and f.fnmatch("%s-*.whl" % dist_name))
    assert len(new_wheels) == 1, "can't find newly created wheel"
    new_wheel = new_wheels[0]

    wheel = wheelhouse.ensure(dir=True).join(new_wheel.basename)
    new_wheel.move(wheel)
    return wheel


def build_egg(wheel, egg_dir):
    from humpty import EggWriter

    print("==== Building egg from %s ====" % wheel)
    egg = EggWriter(str(wheel)).build_egg(str(egg_dir))
    return py.path.local(egg)


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
            if unzip:
                cmd.append('--always-unzip')
            cmd.extend(install)
            self.check_call(cmd)

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
