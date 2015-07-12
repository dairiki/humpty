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
import py_compile
import shutil
import sys
import tempfile
from textwrap import dedent
from zipfile import ZipFile, ZIP_DEFLATED

import click
from distlib.markers import interpret
from distlib.metadata import LegacyMetadata
import distlib.scripts
from distlib.util import get_export_entry
from distlib.wheel import Wheel
import pkg_resources

log = logging.getLogger(__name__)


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


class EggMetadata(object):
    """ Compute egg metadata.

    An instance of this class is an iterable of ``filename, content``
    pairs, where each pair represents a metadata file which should be
    written to the packages ``EGG-INFO`` directory.

    """
    def __init__(self, wheel):
        self.wheel = wheel
        self.metadata = wheel.metadata

    def __iter__(self):
        # XXX: dependency_links.txt?
        # XXX: Copy any other *.txt?

        yield 'PKG-INFO', self.pkg_info()

        for name in ('requires', 'top_level', 'entry_points',
                     'namespace_packages', 'native_libs', 'eager_resources'):
            content = getattr(self, name)()
            if content:
                yield "%s.txt" % name, content

        if self.is_zip_safe:
            yield 'zip-safe', ''
        else:
            yield 'not-zip-safe', ''

    @property
    def is_zip_safe(self):
        # FIXME: I'm not at all sure this is correct.
        # There should probably be a command-line argument to override
        # the auto detection of zip-safeness.

        # XXX: py3k seems not to be able to load .pyc from zipped eggs
        if sys.version_info >= (3,):
            return False
        return self.wheel.is_mountable()

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
        txt = self.read_metadata('entry_points.txt')
        if txt is None:
            txt = unsplit_sections(
                (section, list(map("{0[0]} = {0[1]}".format, entries.items())))
                for section, entries in self.metadata.exports)
        return txt

    def namespace_packages(self):
        # FIXME: maybe depend on wheel (or metadata) version?
        txt = self.read_metadata('namespace_packages.txt')
        if txt is None:
            txt = join_lines(self.metadata.namespaces)
        return txt

    def top_level(self):
        # FIXME: maybe depend on wheel (or metadata) version?
        txt = self.read_metadata('top_level.txt')
        assert txt is not None, "not sure what to do"
        # Maybe extract top-level packages from metadata.modules?
        return txt

    def native_libs(self):
        # FIXME: maybe depend on wheel (or metadata) version?
        txt = self.read_metadata('native_libs.txt')
        if txt is None:
            native_libs = []
            with self.open_wheel() as zf:
                for arcname in zf.namelist():
                    base, ext = posixpath.splitext(arcname)
                    if ext.lower() in ('.so', '.dll', '.dylib'):
                        native_libs.append(arcname)
            txt = join_lines(native_libs)
        return txt

    def eager_resources(self):
        # FIXME: maybe depend on wheel (or metadata) version?
        txt = self.read_metadata('eager_resources.txt')
        if txt is None:
            # FIXME: not sure what to do.
            pass
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
        txt = unsplit_sections(sections)
        return txt

    def read_metadata(self, name):
        metadata_path = posixpath.join(
            "%s-%s.dist-info" % (self.wheel.name, self.wheel.version),
            name)
        with self.open_wheel() as zf:
            try:
                with fh(zf.open(metadata_path)) as fp:
                    return fp.read().decode('utf-8')
            except KeyError:
                return None

    @contextmanager
    def open_wheel(self):
        wheel = self.wheel
        wheel_file = os.path.join(wheel.dirname, wheel.filename)
        zf = ZipFile(wheel_file, 'r')
        try:
            yield zf
        finally:
            zf.close()


class StubLoaders(object):
    """ Generate stub loaders.

    Generate stub loaders for namespace packages and extension modules.

    An instance of this class is an iterable of ``filename, content``
    pairs, where each pair represents a stub-loader file which should be
    written to the packages egg.

    """
    NAMESPACE_STUB = dedent("""
        try:
            __import__('pkg_resources').declare_namespace(__name__)
        except ImportError:
            __path__ = __import__('pkgutil').extend_path(__path__, __name__)
        """).lstrip()

    EXT_STUB_TEMPLATE = dedent("""
        def __bootstrap__():
            global __bootstrap__, __loader__, __file__
            import sys, pkg_resources, imp
            __file__ = pkg_resources.resource_filename(__name__, {extname!r})
            __loader__ = None; del __bootstrap__, __loader__
            imp.load_dynamic(__name__,__file__)
        __bootstrap__()
        """).lstrip()

    def __init__(self, egg_metadata, egg_name=''):
        self.egg_metadata = egg_metadata
        self.egg_name = egg_name

    def __iter__(self):
        if sys.version_info < (3, 3):
            stubs = self.namespace_stubs()
        else:
            stubs = ()          # PEP 420

        if self.egg_metadata.is_zip_safe:
            stubs = chain(stubs, self.extension_stub_loaders())

        for arcname, content in stubs:
            yield arcname, content
            yield self.byte_compile(arcname, content)

    def namespace_stubs(self):
        """ Create __init__.py for namespace packages
        """
        content = self.NAMESPACE_STUB.encode('utf-8')
        namespace_packages = self.egg_metadata.namespace_packages()
        for package in pkg_resources.yield_lines(namespace_packages):
            parts = package.split('.') + ['__init__.py']
            arcname = posixpath.join(*parts)
            yield arcname, content

    def extension_stub_loaders(self):
        """ Stub loaders for extension modules.

        Only needed (I think) if zip_safe is set.

        """
        native_libs = self.egg_metadata.native_libs()
        for extmod in pkg_resources.yield_lines(native_libs):
            head, extname = posixpath.split(extmod)
            root, ext = posixpath.splitext(extmod)
            stubname = root + '.py'
            stub_loader = self.EXT_STUB_TEMPLATE.format(extname=extname)
            content = stub_loader.encode('utf-8')
            yield stubname, content

    def byte_compile(self, arcname, content):
        root, ext = posixpath.splitext(arcname)
        arcname_pyc = root + '.pyc'
        diagnostic_name = posixpath.join(self.egg_name, arcname)
        with tempfile.NamedTemporaryFile() as dst:
            with tempfile.NamedTemporaryFile() as src:
                src.write(content)
                src.flush()
                py_compile.compile(src.name, dst.name, diagnostic_name, True)
            return arcname_pyc, dst.read()


class EggWriter(object):
    def __init__(self, wheel_file):
        wheel = Wheel(wheel_file)
        assert wheel.is_compatible()
        wheel.verify()

        self.wheel = wheel

    def build_egg(self, destdir):
        wheel = self.wheel
        outfile = os.path.join(destdir, self.egg_name)
        egg_metadata = EggMetadata(wheel)
        log.warning("Converting %s to %s", wheel.filename, outfile)

        if not os.path.isdir(destdir):
            log.info("Creating dist directory %s", destdir)
            os.makedirs(destdir)

        with fh(ZipFile(outfile, 'w', ZIP_DEFLATED)) as zf:
            builddir = tempfile.mkdtemp()
            try:
                for arcname, filename in self.unpack_wheel(builddir):
                    zf.write(filename, arcname)
            finally:
                shutil.rmtree(builddir)

            stub_loaders = StubLoaders(egg_metadata, self.egg_name)
            for arcname, content in stub_loaders:
                zf.writestr(arcname, content)

            for filename, content in egg_metadata:
                arcname = 'EGG-INFO/%s' % filename
                zf.writestr(arcname, content)

        return outfile

    def unpack_wheel(self, libdir):
        wheel = self.wheel
        name_version = '%s-%s' % (wheel.name, wheel.version)
        data_dir = os.path.join(libdir, '%s.data' % name_version)
        egginfo_dir = os.path.join(libdir, 'EGG-INFO')
        paths = {
            'purelib': libdir,
            'platlib': libdir,
            'scripts': os.path.join(egginfo_dir, 'scripts'),
            }
        for where in 'prefix', 'headers', 'data':
            paths[where] = os.path.join(data_dir, where)

        for path in paths.values():
            if not os.path.isdir(path):
                log.debug("Creating directory %s", path)
                os.makedirs(path)

        maker = ScriptCopyer(None, None)
        wheel.install(paths, maker, warner=warner)

        subdirs = [()]
        while subdirs:
            path = subdirs.pop(0)
            for fn in os.listdir(os.path.join(libdir, *path)):
                topdir = len(path) == 0
                fpath = path + (fn,)
                filepath = os.path.join(libdir, *fpath)
                if os.path.isdir(filepath):
                    if topdir and fn.lower().endswith('.dist-info'):
                        # Omit .dist-info directory
                        continue
                    subdirs.append(fpath)
                else:
                    if topdir and fn.endswith('-nspkg.pth'):
                        # Omit *-nspkg.pth file
                        continue
                    arcname = posixpath.join(*fpath)
                    yield arcname, filepath

    @property
    def egg_name(self):
        wheel = self.wheel
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
    '-d', '--dist-dir',
    type=click.Path(writable=True, file_okay=False),
    default='dist',
    help="Build eggs into <dir>.  Default is <cwd>/dist.",
    metavar='DIR',
    )
@click.argument(
    'wheels',
    nargs=-1,
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    )
def main(dist_dir, wheels):
    """ Convert wheels to eggs.
    """

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    for wheel in wheels:
        EggWriter(wheel).build_egg(dist_dir)


if __name__ == '__main__':
    main()                      # pragma: NO COVER
