#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (C) Geoffrey T. Dairiki
""" A tool to convert wheels to eggs.
"""
from __future__ import absolute_import

from contextlib import contextmanager
from io import StringIO
from itertools import chain
import logging
import os
import posixpath
import shutil
import sys
import tempfile
from zipfile import ZipFile

import click
from distlib.markers import interpret
from distlib.metadata import LegacyMetadata
import distlib.scripts
from distlib.util import get_export_entry, zip_dir, FileOperator
from distlib.wheel import Wheel
import pkg_resources

log = logging.getLogger(__name__)

NAMESPACE_INIT = """
try:
    __import__('pkg_resources').declare_namespace(__name__)
except ImportError:
    __path__ = __import__('pkgutil').extend_path(__path__, __name__)
""".lstrip()


@contextmanager
def fh(fp):
    try:
        yield fp
    finally:
        fp.close()


def unsplit_sections(sections):
    """ This is essentially the inverse of pkg_resources.split_sections.
    """
    lines = []
    for section, content in sections:
        if section is not None:
            lines.append("[%s]" % section)
        lines.extend(content)
    return join_lines(lines)


def join_lines(lines):
    return '\n'.join(list(lines) + [''])


class EggInfo(object):
    def __init__(self, wheel):
        self.wheel = wheel
        self.metadata = wheel.metadata

    def __iter__(self):
        # FIXME: scripts?
        # FIXME: copy from distinfo_dir to egginfo_dir
        # - ?dependency_links.txt
        # ?All *.txt?
        # FIXME: Generate native_libs.txt
        # FIXME: Generate eager_resources.txt?

        yield 'PKG-INFO', self.pkg_info()
        yield 'requires.txt', self.requires()
        yield 'top_level.txt', self.top_level()

        entry_points = self.entry_points()
        if entry_points:
            yield 'entry_points.txt', entry_points

        namespace_packages = self.namespace_packages()
        if namespace_packages:
            yield 'namespace_packages.txt', namespace_packages

        zip_safe = self.wheel.is_mountable()
        # FIXME: need command-line override for zip-safe
        if zip_safe:
            yield 'zip-safe', ''
        else:
            yield 'not-zip-safe', ''

    def pkg_info(self):
        # FIXME: Which Metadata version?
        # FIXME: Description is missing
        fp = StringIO()
        egg_md = LegacyMetadata(mapping=self.metadata.todict())
        egg_md.check(strict=True)
        egg_md.write_file(fp, skip_unknown=True)
        return fp.getvalue()

    def entry_points(self):
        # FIXME: maybe depend on wheel (or metadata) version to determine
        # which method to use to get data
        txt = self.read_info('entry_points.txt')
        if txt is None:
            txt = unsplit_sections(
                (section, list(map("{0[0]} = {0[1]}".format, entries.items())))
                for section, entries in self.metadata.exports)
        return txt

    def namespace_packages(self):
        # FIXME: maybe depend on wheel (or metadata) version?
        txt = self.read_info('namespace_packages.txt')
        if txt is None:
            txt = join_lines(self.metadata.namespaces)
        return txt

    def top_level(self):
        # FIXME: maybe depend on wheel (or metadata) version?
        txt = self.read_info('top_level.txt')
        assert txt is not None, "not sure what to do"
        # Maybe extract top-level packages from metadata.modules?
        return txt

    def requires(self):
        run_requires = self.metadata.run_requires

        def filter_reqs(extra, req):
            if isinstance(req, dict):
                if req.get('extra') == extra:
                    marker = req.get('environment')
                    if not marker or interpret(marker):
                        return req['requires']
            else:
                req_, sep, marker = req.rpartition(';')
                if not sep:
                    return [req]
                elif interpret(marker, {'extra': extra}):
                    return [req_]
            return []

        def reqs(extra=None):
            return chain.from_iterable(filter_reqs(extra, req)
                                       for req in run_requires)

        requires = list(reqs())
        unconditional = set(requires)
        sections = [(None, requires)]

        for extra in self.metadata.extras:
            sections.append((extra, [req for req in reqs(extra)
                                     if req not in unconditional]))
        return unsplit_sections(sections)

    def read_info(self, filename):
        wheel = self.wheel
        pathname = os.path.join(wheel.dirname, wheel.filename)
        info_dir = "%s-%s.dist-info" % (wheel.name, wheel.version)
        path = posixpath.join(info_dir, filename)
        with fh(ZipFile(pathname, 'r')) as zf:
            try:
                with fh(zf.open(path)) as fp:
                    return fp.read().decode('utf-8')
            except KeyError:
                return None


class EggWriter(object):
    def __init__(self, wheel_file):
        wheel = Wheel(wheel_file)
        assert wheel.is_compatible()
        wheel.verify()

        self.wheel = wheel
        self.fileops = FileOperator()  # FIXME: dry-run?

    def build_egg(self, destdir):
        wheel = self.wheel
        egg_name = self.get_egg_name(wheel)
        outfile = os.path.join(destdir, egg_name)
        log.warning("Converting %s to %s", wheel.filename, egg_name)
        builddir = tempfile.mkdtemp()
        try:
            self.unpack_wheel(wheel, builddir)
            zf = zip_dir(builddir)
            zf.seek(0)
            self.fileops.copy_stream(zf, outfile)
            return outfile
        finally:
            shutil.rmtree(builddir)

    def unpack_wheel(self, wheel, builddir):
        fileops = self.fileops
        libdir = builddir
        name_version = '%s-%s' % (wheel.name, wheel.version)
        data_dir = os.path.join(libdir, '%s.data' % name_version)
        distinfo_dir = os.path.join(libdir, '%s.dist-info' % name_version)
        egginfo_dir = os.path.join(libdir, 'EGG-INFO')
        paths = {
            'purelib': libdir,
            'platlib': libdir,
            'scripts': os.path.join(egginfo_dir, 'scripts'),
            }
        for where in 'prefix', 'headers', 'data':
            paths[where] = os.path.join(data_dir, where)

        map(fileops.ensure_dir, paths.values())

        maker = ScriptCopyer(None, None)
        wheel.install(paths, maker, warner=warner)

        # Create files in EGG-INFO
        egg_info = EggInfo(wheel)
        for filename, content in egg_info:
            outfile = os.path.join(egginfo_dir, filename)
            log.info("Creating %s", outfile)
            fileops.write_text_file(outfile, content, 'utf-8')

        # Create __init__.py for namespace packages
        for package in pkg_resources.yield_lines(
                egg_info.namespace_packages()):
            parts = package.split('.')
            outfile = os.path.join(os.path.join(libdir, *parts),
                                   '__init__.py')
            log.info("Creating %s", outfile)
            fileops.write_text_file(outfile, NAMESPACE_INIT, 'utf-8')
            fileops.byte_compile(outfile)

        # Remove *-nspkg.pth file
        pthfiles = [os.path.join(libdir, fn)
                    for fn in os.listdir(libdir)
                    if fn.lower().endswith('-nspkg.pth')]
        if pthfiles:
            assert len(pthfiles) == 1
            for pthfile in pthfiles:
                fileops.ensure_removed(pthfile)

        # Remove .dist-info directory
        fileops.ensure_removed(distinfo_dir)

    def get_egg_name(self, wheel):
        name = pkg_resources.safe_name(wheel.name)
        version = pkg_resources.safe_version(wheel.version)
        pyver = 'py%d.%d' % sys.version_info[:2]
        bits = [pkg_resources.to_filename(name),
                pkg_resources.to_filename(version),
                pyver]
        if any(abi != 'none' or arch != 'any'
               for pyver, abi, arch in wheel.tags):
            # not pure python
            bits.append(pkg_resources.get_build_platform())
        return '-'.join(bits) + '.egg'


def warner(software_wheel_version, file_wheel_version):
    log.info("Wheel version mismatch: software=%r, file=%r",
             software_wheel_version, file_wheel_version)


class ScriptCopyer(distlib.scripts.ScriptMaker):
    """ A ScriptMaker which does not create script wrappers.

    It does copy the """
    def make(self, specification, options=None):
        if get_export_entry(specification):
            log.debug("Not building script: %s", specification)
            return []
        return super(ScriptCopyer, self).make(specification, options)


@click.command()
@click.option(
    '-d', '--egg-dir', default='dist',
    type=click.Path(writable=True, file_okay=False),
    help="Build eggs into <dir>.  Default is <cwd>/dist.",
    metavar='DIR')
@click.argument(
    'wheels', type=click.Path(exists=True, dir_okay=False),
    nargs=-1, required=True)
def main(egg_dir, wheels):
    """ Convert wheels to eggs.

    """
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    for wheel in wheels:
        EggWriter(wheel).build_egg(egg_dir)


if __name__ == '__main__':
    main()
