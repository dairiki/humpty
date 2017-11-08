#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (C) Geoffrey T. Dairiki
""" A tool to convert wheels to eggs.
"""
from __future__ import absolute_import

from collections import defaultdict
import email
import imp
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
import distlib.scripts
from distlib.util import get_export_entry
from distlib.wheel import Wheel
import pkg_resources
from six import binary_type, text_type, PY3

log = logging.getLogger(__name__)

try:
    from importlib.util import cache_from_source
except ImportError:             # python < 3.4
    try:
        from imp import cache_from_source
    except ImportError:         # python < 3.2
        def cache_from_source(path):
            root, ext = os.path.splitext(path)
            return root + '.pyc'

try:
    import sysconfig
except ImportError:            # pragma: NO COVER
    # python < 2.7
    # FIXME: incorrect on non-posix systems
    EXT_SUFFIX = '.so'
else:
    EXT_SUFFIX = (sysconfig.get_config_var('EXT_SUFFIX')
                  or sysconfig.get_config_var('SO'))


class file_cm(object):
    """ Add context manager methods to dumb file-like instances.

    """
    def __init__(self, fp):
        self._fp = fp

    def __enter__(self):
        return self._fp

    def __exit__(self, typ, inst, tb):
        self._fp.close()

    def __getattr__(self, name):
        return getattr(self._fp, name)


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
    return '\n'.join(list(lines) + ['']).encode('utf-8')


def bytes_(s, encoding='latin1', errors='strict'):
    if not isinstance(s, binary_type):
        s = s.encode(encoding, errors)
    return s


def _get_requires_json(wheel_metadata):
    """ Compute requirements, grouped by extra.

    This expects wheel_metadata.run_requires to be in the JSON format
    as described at
    https://www.python.org/dev/peps/pep-0426/#dependencies

    """
    by_extra = defaultdict(set)
    for req in wheel_metadata.run_requires:
        extra = req.get('extra')
        marker = req.get('environment')
        if not marker or interpret(marker):
            by_extra[extra].update(req['requires'])

    for extra in sorted(by_extra.keys(),
                        key=lambda extra: (extra is not None, extra)):
        yield extra, sorted(by_extra[extra])


def _get_requires_rfc822(wheel_metadata):
    """ Compute requirements, grouped by extra.

    This expects wheel_metadata.run_requires to be a list of strings,
    as when metadata comes from legacy RFC822 formatted metadata.

    """
    run_requires = wheel_metadata.run_requires

    def get_reqs(extra=None):
        for req in run_requires:
            assert isinstance(req, text_type)
            req_, sep, marker = req.rpartition(';')
            if not sep:
                yield req
            elif interpret(marker.lstrip(), {'extra': extra}):
                yield req_.rstrip()

    reqs = list(get_reqs())
    if reqs:
        yield None, reqs

    unconditional = set(reqs)
    is_conditional = lambda req: req not in unconditional

    for extra in wheel_metadata.extras:
        reqs = list(filter(is_conditional, get_reqs(extra)))
        if reqs:
            yield extra, reqs


class EggInfoBase(object):
    """ Egg metadata.

    An instance of this class is an iterable of ``filename, content``
    pairs, where each pair represents a metadata file which should be
    written to the packages ``EGG-INFO`` directory.

    """
    def __init__(self, wheel_metadata, installed_files, metadata_files,
                 zip_safe=False):
        self.wheel_metadata = wheel_metadata
        self.installed_files = installed_files
        self.metadata_files = metadata_files
        self.zip_safe = zip_safe

    def files(self):
        # XXX: dependency_links.txt?

        yield 'PKG-INFO', join_lines(self.pkg_info)

        for name in ('requires', 'entry_points'):
            sections = getattr(self, name)
            if sections:
                yield "%s.txt" % name, unsplit_sections(sections)

        for name in ('top_level', 'namespace_packages',
                     'native_libs', 'eager_resources'):
            lines = getattr(self, name)
            if lines:
                yield "%s.txt" % name, join_lines(lines)

        if self.zip_safe:
            yield 'zip-safe', b''
        else:
            yield 'not-zip-safe', b''

    __iter__ = files

    @property
    def pkg_info(self):
        index_data = self._get_index_data()

        yield "Metadata-Version: 1.1"

        for name in ("Name", "Version", "Summary", "Home-page",
                     "Author", "Author-email", "License"):
            key = name.lower().replace('-', '_')
            yield "%s: %s" % (name, index_data.get(key, 'UNKNOWN'))

        if 'download_url' in index_data:
            yield "Download-URL: %s" % index_data['download_url']

        description = index_data.get('description', 'UNKNOWN').split('\n')
        yield "Description: %s" % description[0]
        for continuation in description[1:]:
            yield "        %s" % continuation

        if 'keywords' in index_data:
            yield "Keywords: %s" % ','.join(index_data['keywords'])

        for platform in index_data.get('platform', ['UNKNOWN']):
            yield "Platform: %s" % platform

        if 'classifiers' in index_data:
            for classifier in index_data['classifiers']:
                yield "Classifier: %s" % classifier

    def _get_index_data(self):
        return self.wheel_metadata.todict()

    @property
    def entry_points(self):     # pragma: NO COVER
        raise NotImplementedError()

    @property
    def namespace_packages(self):  # pragma: NO COVER
        raise NotImplementedError()

    @property
    def top_level(self):
        top_level = set()
        for path in self.installed_files:
            lpath = path.lower()
            for suffix in ('.py', EXT_SUFFIX):
                if lpath.endswith(suffix):
                    root = path[:-len(suffix)]
                    break
            else:
                continue
            top, sep, tail = root.partition('/')
            top_level.add(top)
        return sorted(top_level)

    @property
    def native_libs(self):
        # wheel (at least as of 0.24.0) does not generate a native_libs.txt
        def is_ext_mod(fn):
            root, ext = posixpath.splitext(fn)
            return ext.lower() in ('.so', '.dll', '.dylib')
        return sorted(set(filter(is_ext_mod, self.installed_files)))

    def eager_resources(self):  # pragma: NO COVER
        raise NotImplementedError()

    def requires(self):         # pragma: NO COVER
        raise NotImplementedError()


class EggInfo_Legacy(EggInfoBase):
    """Compute egg metadata from PEP427 Wheel 1.0 metadata.

    This is for ``.whl`` produced by the current version (0.24.0) of
    ``wheel``\s ``bdist_wheel`` setup command.  It uses the
    ``METADATA`` which purports to be of metadata version 2.0, but is
    in the RFC822 format, rather than JSON as specified by :pep:`426`.

    """
    def _get_index_data(self):
        index_data = super(EggInfo_Legacy, self)._get_index_data()
        description = index_data.get('description')
        if description is None:
            # distlib (as of 0.2.1) does not manage to parse the
            # description from the METADATA files written by wheel's
            # bdist_wheel.
            description = self._get_description()
        else:
            # Setuptools writes the description with continuation
            # lines indented eight spaces.  Distlib expects
            # continuation lines to be prefixed by seven spaces and a
            # pipe (per PEP 345.)  As a result distlib does not seem
            # to remove setuptools' eight space prefixes :-/
            description = '\n'.join(
                line[8:] if line.startswith(' ' * 8) else line
                for line in description.strip().splitlines()
                )
        index_data['description'] = description
        return index_data

    def _get_description(self):
        log.debug("Reading description from METADATA")
        metadata = self.metadata_files['METADATA']
        # NB: Under py3k, message_from_file seems to want a str, but
        # with bytes in it (not characters.)
        if PY3:                 # pragma: NO COVER
            metadata = metadata.decode('latin1')
        msg = email.message_from_string(metadata)
        body = msg.get_payload(decode=True)
        return bytes_(body).decode('utf-8')

    @property
    def entry_points(self):
        sections = pkg_resources.split_sections(
            self._read_metadata('entry_points.txt'))
        return [(section, lines) for section, lines in sections if lines]

    @property
    def namespace_packages(self):
        return list(self._read_metadata('namespace_packages.txt'))

    @property
    def top_level(self):
        # FIXME: maybe depend on wheel version?
        if self._metadata_exists('top_level.txt'):
            return list(self._read_metadata('top_level.txt'))
        else:
            # wheel < 0.10 does not write a top_level.txt
            return super(EggInfo_Legacy, self).top_level

    @property
    def eager_resources(self):
        return list(self._read_metadata('eager_resources.txt'))

    @property
    def requires(self):
        wheel_metadata = self.wheel_metadata
        is_legacy = wheel_metadata._legacy is not None
        if is_legacy:
            # With older versions of distlib, when reading wheels
            # built with older versions of wheel,
            # metadata.run_requires is a list of strings in the RFC822
            # metadata style.
            # (E.g. distlib==0.2.4, wheel==0.25.0)
            get_requires = _get_requires_rfc822
        else:
            # With recent versions of distlib, or with wheels built
            # by recent versions of wheel, run_requires is a list of dicts
            # in the "JSON" format described by PEP-426.
            get_requires = _get_requires_json

        return list(get_requires(wheel_metadata))

    def _read_metadata(self, name):
        """ Read a .txt format metadata file from .whl file.
        """
        content = self.metadata_files.get(name, b'')
        content = content.decode('utf-8')
        return pkg_resources.yield_lines(content)

    def _metadata_exists(self, name):
        return name in self.metadata_files


class EggInfo(EggInfoBase):
    """ Compute egg metadata from PEP491 Wheel 1.1? metadata.

    This uses the JSON metadata version 2.0 as specified in :pep:`426`.

    **NB**: Currently, I know of know packages which produce wheels of
    this type, so this code is untested.

    """
    @property
    def entry_points(self):
        return [
            (section, ["%s = %s" % item for item in entries.items()])
            for section, entries in self.wheel_metadata.exports.items()
            ]

    @property
    def namespace_packages(self):
        return self.wheel_metadata.namespaces

    @property
    def eager_resources(self):
        # FIXME: not sure what to do.
        return []

    @property
    def requires(self):
        return list(_get_requires_json(self.wheel_metadata))


def list_installed_files(wheel):
    wheel_file = os.path.join(wheel.dirname, wheel.filename)
    info_pfx = "{0.name}-{0.version}.dist-info/".format(wheel)
    data_pfx = "{0.name}-{0.version}.data/".format(wheel)
    purelib_pfx = "{0.name}-{0.version}.data/purelib/".format(wheel)
    platlib_pfx = "{0.name}-{0.version}.data/platlib/".format(wheel)

    installed = set()
    with file_cm(ZipFile(wheel_file, 'r')) as zf:
        for path in zf.namelist():
            if path.endswith('/'):
                # directory
                continue        # pragma: NO COVER
            elif path.startswith(info_pfx):
                continue
            elif path.startswith(purelib_pfx):
                installed_path = path[len(purelib_pfx):]
            elif path.startswith(platlib_pfx):
                installed_path = path[len(platlib_pfx):]
            elif path.startswith(data_pfx):
                continue
            else:
                installed_path = path
            installed.add(installed_path)
    return installed


def read_metadata_files(wheel):
    wheel_file = os.path.join(wheel.dirname, wheel.filename)
    info_pfx = "{0.name}-{0.version}.dist-info/".format(wheel)
    metadata_files = {}
    with file_cm(ZipFile(wheel_file, 'r')) as zf:
        for path in zf.namelist():
            if path.startswith(info_pfx) and not path.endswith('/'):
                with file_cm(zf.open(path)) as fp:
                    name = path[len(info_pfx):]
                    metadata_files[name] = fp.read()
    return metadata_files


def is_zip_safe(wheel):
    # XXX: Py3k seems not to be able to load .pyc from zipped eggs.
    # More specifically, it will load .pyc files which are placed next
    # to their .py files (old-style), however compiled byte-code in
    # :pep:`3147` style *repository directories* (__pycache__) seem
    # not be loaded from a zip file.  OTOH, zipped eggs generated by
    # setuptools bdist_egg command suffer the same issue.  Punt for
    # now...

    # FIXME: currently distlib's WHEEL.is_mountable always
    # returns true
    #
    # Note that currently this function is unused.
    return wheel.is_mountable()


def get_wheel_version(wheel):
    return tuple(map(int, wheel.info['Wheel-Version'].split('.')))


def egg_metadata(wheel, egg_metadata_class=None):
    if get_wheel_version(wheel) < (1, 1):
        egg_metadata_class = EggInfo_Legacy
    else:
        egg_metadata_class = EggInfo

    return egg_metadata_class(
        wheel.metadata,
        installed_files=list_installed_files(wheel),
        metadata_files=read_metadata_files(wheel),
        zip_safe=False)


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

    def __init__(self, egg_info, egg_name=''):
        self.egg_info = egg_info
        self.egg_name = egg_name

    def __iter__(self):
        # XXX: don't need namespace stubs for py3k, if egg is unpacked,
        # however they are still necessary if running from zipped egg.
        # For now, always include them.
        stubs = self.namespace_stubs()
        if self.egg_info.zip_safe:
            stubs = chain(stubs, self.extension_stub_loaders())

        for arcname, content in stubs:
            yield arcname, content
            yield self.byte_compile(arcname, content)

    def namespace_stubs(self):
        """ Create __init__.py for namespace packages
        """
        content = self.NAMESPACE_STUB.encode('utf-8')
        for package in self.egg_info.namespace_packages:
            parts = package.split('.') + ['__init__.py']
            arcname = posixpath.join(*parts)
            yield arcname, content

    def extension_stub_loaders(self):
        """ Stub loaders for extension modules.

        Only needed (I think) if zip_safe is set.

        """
        for extmod in self.egg_info.native_libs:
            if extmod.endswith(EXT_SUFFIX):
                head, extname = posixpath.split(extmod)
                stubname = extmod[:-len(EXT_SUFFIX)] + '.py'
                stub_loader = self.EXT_STUB_TEMPLATE.format(extname=extname)
                content = stub_loader.encode('utf-8')
                yield stubname, content

    def byte_compile(self, arcname, content):
        py_path = os.path.join(*arcname.split('/'))
        pyc_path = cache_from_source(py_path)
        arcname_pyc = '/'.join(pyc_path.split(os.path.sep))

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
        assert wheel.is_compatible(), \
            "%s is not compatible with this platform" % wheel_file
        wheel.verify()

        self.wheel = wheel

    def build_egg(self, destdir):
        wheel = self.wheel
        outfile = os.path.join(destdir, self.egg_name)
        egg_info = egg_metadata(wheel)
        log.warning("Converting %s to %s", wheel.filename, outfile)

        if not os.path.isdir(destdir):
            log.info("Creating dist directory %s", destdir)
            os.makedirs(destdir)

        with file_cm(ZipFile(outfile, 'w', ZIP_DEFLATED)) as zf:
            builddir = tempfile.mkdtemp()
            try:
                for arcname, filename in self.unpack_wheel(builddir):
                    zf.write(filename, arcname)
            finally:
                shutil.rmtree(builddir)

            stub_loaders = StubLoaders(egg_info, self.egg_name)
            for arcname, content in stub_loaders:
                zf.writestr(arcname, content)

            for filename, content in egg_info:
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

    It does copy the scripts from the source.
    """
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
