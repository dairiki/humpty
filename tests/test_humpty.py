# -*- coding: utf-8 -*-
""" Unit tests.
"""
from __future__ import absolute_import

import imp
import os
import posixpath
import sys
from zipfile import ZipFile

import pytest
from six import int2byte, unichr, StringIO

try:
    import sysconfig
except ImportError:             # python < 2.7
    # FIXME: incorrect on non-posix systems
    EXT_SUFFIX = '.so'
else:
    EXT_SUFFIX = (sysconfig.get_config_var('EXT_SUFFIX')
                  or sysconfig.get_config_var('SO'))


class test_cache_from_source():
    from humpty import cache_from_source
    if sys.version_info >= (3, 2):
        tag = imp.get_tag()
        assert cache_from_source('foo.py') == os.path.join('__pycache__',
                                                           'foo.%s.pyc' % tag)
    else:
        assert cache_from_source('foo.py') == 'foo.pyc'


class Test_file_cm(object):
    def make_one(self, fp):
        from humpty import file_cm
        return file_cm(fp)

    def test_closes_file(self):
        with self.make_one(StringIO()) as fp:
            assert not fp.closed
        assert fp.closed

    def test_proxy(self):
        fp = StringIO()
        proxy = self.make_one(fp)
        proxy.write('x')
        assert fp.getvalue() == 'x'


def test_unsplit_sections():
    from humpty import unsplit_sections
    content = unsplit_sections([
        (None, ['a', 'b']),
        ('foo', ['c']),
        ])
    assert content == (b"a\n"
                       b"b\n"
                       b"[foo]\n"
                       b"c\n")


def test_join_lines():
    from humpty import join_lines
    assert join_lines(['a', 'b']) == b'a\nb\n'
    assert join_lines([u'ø']) == b'\xc3\xb8\n'


def test_bytes():
    from humpty import bytes_
    all_bytes = b''.join(map(int2byte, range(256)))
    chars256 = ''.join(map(unichr, range(256)))
    assert bytes_(all_bytes) == all_bytes
    assert bytes_(chars256) == all_bytes


class DummyWheelMetadata(object):
    exports = {}
    namespaces = []
    extras = []
    run_requires = []
    index_data = {}

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def todict(self):
        return self.index_data


class EggInfoTestBase(object):
    @pytest.fixture
    def index_data(self):
        return {}

    @pytest.fixture
    def wheel_metadata(self, index_data):
        return DummyWheelMetadata(index_data=index_data)

    @pytest.fixture
    def installed_files(self):
        return set([])

    @pytest.fixture
    def metadata_files(self):
        return {
            'METADATA': b'',
            }

    def test_files(self, egg_info, wheel_metadata):
        egg_info.zip_safe = True
        pkg_info = '\n'.join(egg_info.pkg_info) + '\n'
        assert dict(egg_info.files()) == {
            'PKG-INFO': pkg_info.encode('utf-8'),
            'zip-safe': b"",
            }

    def test_files_zip_safe(self, egg_info):
        egg_info.zip_safe = True
        files = dict(egg_info.files())
        assert files['zip-safe'] == b''
        assert 'not-zip-safe' not in files

    def test_files_not_zip_safe(self, egg_info):
        egg_info.zip_safe = False
        files = dict(egg_info.files())
        assert files['not-zip-safe'] == b''
        assert 'zip-safe' not in files

    def test_pkg_info(self, egg_info, index_data):
        index_data.update({
            'name': 'dummy',
            'version': '3.2.1',
            'author': 'Joe',
            'author_email': 'joe@example.com',
            'description': 'Line 1\nLine 2',
            })
        assert list(egg_info.pkg_info) == [
            'Metadata-Version: 1.1',
            'Name: dummy',
            'Version: 3.2.1',
            'Summary: UNKNOWN',
            'Home-page: UNKNOWN',
            'Author: Joe',
            'Author-email: joe@example.com',
            'License: UNKNOWN',
            'Description: Line 1',
            '        Line 2',
            'Platform: UNKNOWN',
            ]

    def test_pkg_info_download_url(self, egg_info, index_data):
        index_data['download_url'] = 'http://example.org'
        assert 'Download-URL: http://example.org' in egg_info.pkg_info

    def test_pkg_info_description(self, egg_info, index_data):
        index_data['description'] = "Line 1\nLine 2"
        pkg_info = list(egg_info.pkg_info)
        i = pkg_info.index('Description: Line 1')
        assert pkg_info[i+1] == '        Line 2'

    def test_pkg_info_keywords(self, egg_info, index_data):
        index_data['keywords'] = ['a', 'b']
        assert 'Keywords: a,b' in egg_info.pkg_info

    def test_pkg_info_platform(self, egg_info, index_data):
        index_data['platform'] = ['foo', 'bar']
        assert 'Platform: foo' in egg_info.pkg_info
        assert 'Platform: bar' in egg_info.pkg_info
        assert 'Platform: UNKNOWN' not in egg_info.pkg_info

    def test_pkg_info_classifiers(self, egg_info, index_data):
        index_data['classifiers'] = ['foo', 'bar']
        assert 'Classifier: foo' in egg_info.pkg_info
        assert 'Classifier: bar' in egg_info.pkg_info
        assert 'Classifier: UNKNOWN' not in egg_info.pkg_info


class TestEggInfo_Legacy(EggInfoTestBase):
    @pytest.fixture
    def egg_info(self, wheel_metadata, installed_files, metadata_files):
        from humpty import EggInfo_Legacy
        return EggInfo_Legacy(wheel_metadata, installed_files, metadata_files)

    def test_files_requires_txt(self, egg_info, wheel_metadata):
        wheel_metadata.run_requires = ['req']
        files = dict(egg_info.files())
        assert files['requires.txt'] == b'req\n'

    def test_files_namespace_packages_txt(self, egg_info, metadata_files):
        metadata_files['namespace_packages.txt'] = b'foo\nfoo.bar\n'
        files = dict(egg_info.files())
        assert files['namespace_packages.txt'] == b'foo\nfoo.bar\n'

    def test_get_index_data(self, egg_info):
        assert 'description' in egg_info._get_index_data()

    def test_get_index_data_existing_description(self, egg_info, index_data):
        index_data['description'] = 'Test'
        assert egg_info._get_index_data()['description'] == 'Test'

    def test_get_description(self, egg_info, metadata_files):
        metadata_files['METADATA'] = (
            u"Metadata-Version: 1.1\n"
            u"Name: something\n"
            u"\n"
            u"Fü\n"
            u"Line 2\n"
            ).encode('utf-8')
        assert egg_info._get_description() == u"Fü\nLine 2\n"

    def test_entry_points(self, egg_info, metadata_files):
        metadata_files['entry_points.txt'] = (
            b"# testing\n"
            b"[console_scripts]\n"
            b"mycmd = foo:main\n"
            )
        assert egg_info.entry_points == [
            ('console_scripts', ["mycmd = foo:main"]),
            ]

    def test_entry_points_empty(self, egg_info):
        assert egg_info.entry_points == []

    def test_namespace_packages(self, egg_info, metadata_files):
        metadata_files['namespace_packages.txt'] = b'foo\n#x\nfoo.bar\n'
        assert egg_info.namespace_packages == ['foo', 'foo.bar']

    def test_top_level(self, egg_info, metadata_files):
        metadata_files['top_level.txt'] = b'foo\n'
        assert egg_info.top_level == ['foo']

    def test_top_level_fallback(self, egg_info, installed_files):
        installed_files.add('bar/baz.py')
        assert egg_info.top_level == ['bar']

    def test_eager_resources(self, egg_info, metadata_files):
        metadata_files['eager_resources.txt'] = b'foo/data.txt\n'
        assert egg_info.eager_resources == ['foo/data.txt']

    def test_requires(self, egg_info, wheel_metadata):
        wheel_metadata.run_requires = [
            "foo",
            "bar ; extra == 'addon'",
            'baz ; extra == "addon"',
            ]
        wheel_metadata.extras = ['addon']
        assert egg_info.requires == [
            (None, ['foo']),
            ('addon', ['bar', 'baz']),
            ]


class TestEggInfo(EggInfoTestBase):
    @pytest.fixture
    def egg_info(self, wheel_metadata, installed_files, metadata_files):
        from humpty import EggInfo
        return EggInfo(wheel_metadata, installed_files, metadata_files)

    def test_files_requires_txt(self, egg_info, wheel_metadata):
        wheel_metadata.run_requires = [{'requires': ['req']}]
        files = dict(egg_info.files())
        assert files['requires.txt'] == b'req\n'

    def test_files_namespace_packages_txt(self, egg_info, wheel_metadata):
        wheel_metadata.namespaces = ['foo', 'foo.bar']
        files = dict(egg_info.files())
        assert files['namespace_packages.txt'] == b'foo\nfoo.bar\n'

    def test_top_level(self, egg_info, installed_files):
        installed_files.update([
            'a/module.py',
            'mod' + EXT_SUFFIX,
            'dir/data.txt',
            'a/b/module.py',
            ])
        assert egg_info.top_level == ['a', 'mod']

    def test_native_libs(self, egg_info, installed_files):
        installed_files.update([
            'a/module.py',
            'a/ext.so',
            'foo.dll',
            ])
        assert egg_info.native_libs == ['a/ext.so', 'foo.dll']

    def test_entry_points(self, egg_info, wheel_metadata):
        wheel_metadata.exports = {
            'console_scripts': {
                'mycmd': 'foo:main',
                },
            }
        assert egg_info.entry_points == [
            ('console_scripts', ["mycmd = foo:main"]),
            ]

    def test_namespace_packages(self, egg_info, wheel_metadata):
        wheel_metadata.namespaces = ['foo', 'foo.bar']
        assert egg_info.namespace_packages == ['foo', 'foo.bar']

    def test_eager_resources(self, egg_info):
        # coverage
        assert egg_info.eager_resources == []

    def test_requires(self, egg_info, wheel_metadata):
        wheel_metadata.run_requires = [
            {
                'requires': ['foo'],
                },
            {
                'extra': 'addon',
                'requires': ['bar', 'baz'],
                },
            ]
        wheel_metadata.extras = ['addon']
        assert egg_info.requires == [
            (None, ['foo']),
            ('addon', ['bar', 'baz']),
            ]


class DummyWheel(object):
    mountable = True

    def __init__(self, **kwargs):
        self.__dict__.update(**kwargs)

    def is_mountable(self):
        return self.mountable


@pytest.fixture
def wheel_files():
    return {
        'mod.py': b'# mod.py\n',
        'pkg/mod2.py': b"# mod2.py\n",
        'distname-1.0.data/purelib/mod3.py': b"# mod3.py\n",
        'distname-1.0.data/platlib/ext' + EXT_SUFFIX: b"",
        'distname-1.0.data/other/junk.txt': b"Junk\n",
        'distname-1.0.dist-info/WHEEL': b"Wheel-Version: 1.0\n",
        'distname-1.0.dist-info/METADATA': b"Metadata-Version: 2.0\n",
        }


@pytest.fixture
def wheel_version():
    return '1.0'


@pytest.fixture
def wheel_is_mountable():
    return True


@pytest.fixture
def dummy_wheel(tmpdir, wheel_files, wheel_version, wheel_is_mountable):
    wheel_file = tmpdir.join('dummy.whl')
    zf = ZipFile(str(wheel_file), 'w')
    for path, content in wheel_files.items():
        zf.writestr(path, content)
    zf.close()
    return DummyWheel(
        name='distname',
        version='1.0',
        dirname=str(tmpdir),
        filename='dummy.whl',
        mountable=wheel_is_mountable,
        info={'Wheel-Version': wheel_version},
        metadata=DummyWheelMetadata())


def test_list_installed_files(dummy_wheel):
    from humpty import list_installed_files
    assert list_installed_files(dummy_wheel) == set([
        'mod.py',
        'pkg/mod2.py',
        'mod3.py',
        'ext' + EXT_SUFFIX,
        ])


def test_read_metadata_files(dummy_wheel):
    from humpty import read_metadata_files
    assert read_metadata_files(dummy_wheel) == {
        'WHEEL': b"Wheel-Version: 1.0\n",
        'METADATA': b"Metadata-Version: 2.0\n",
        }


@pytest.mark.parametrize('wheel_is_mountable', [True, False])
def test_is_zip_safe(dummy_wheel, wheel_is_mountable):
    from humpty import is_zip_safe
    assert is_zip_safe(dummy_wheel) is bool(wheel_is_mountable)


def test_get_wheel_version(dummy_wheel):
    from humpty import get_wheel_version
    assert get_wheel_version(dummy_wheel) == (1, 0)


@pytest.mark.parametrize('wheel_version, egg_info_class', [
    ('1.0', 'EggInfo_Legacy'),
    ('1.1', 'EggInfo'),
    ])
def test_egg_metadata(dummy_wheel, egg_info_class):
    from humpty import egg_metadata
    egg_info = egg_metadata(dummy_wheel)
    assert type(egg_info).__name__ == egg_info_class


class DummyEggInfo(object):
    namespace_packages = []
    native_libs = []
    zip_safe = True

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


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


class TestStubLoaders(object):
    @pytest.fixture
    def egg_info(self):
        return DummyEggInfo()

    @pytest.fixture
    def egg_name(self):
        return 'dummy.egg'

    @pytest.fixture
    def stub_loaders(self, egg_info, egg_name):
        from humpty import StubLoaders
        return StubLoaders(egg_info, egg_name)

    def test_namespace_stubs_for_py2(self, stub_loaders, egg_info):
        egg_info.namespace_packages = ['foo']
        stubs = dict(stub_loaders)
        assert set(stubs) == with_byte_compiled(['foo/__init__.py'])

    def test_extension_stubs(self, stub_loaders, egg_info):
        egg_info.native_libs = ['ext' + EXT_SUFFIX]
        stubs = dict(stub_loaders)
        assert set(stubs) == with_byte_compiled(['ext.py'])

    def test_no_extension_stubs_if_zip_unsafe(self, stub_loaders, egg_info,
                                              monkeypatch):
        egg_info.native_libs = ['ext' + EXT_SUFFIX]
        egg_info.zip_safe = False
        stubs = dict(stub_loaders)
        assert set(stubs) == set([])

    def test_namespace_stubs(self, stub_loaders, egg_info):
        egg_info.namespace_packages = ['foo', 'foo.bar']
        stubs = dict(stub_loaders.namespace_stubs())
        assert set(stubs) == set(['foo/__init__.py', 'foo/bar/__init__.py'])

    def test_extension_stub_loaders(self, stub_loaders, egg_info):
        egg_info.native_libs = ['ext' + EXT_SUFFIX]
        loaders = dict(stub_loaders.extension_stub_loaders())
        assert set(loaders) == set(['ext.py'])


def test_warner(caplog):
    # coverage
    from humpty import warner
    warner((1, 2), (1, 0))
    assert "Wheel version mismatch" in caplog.text()


class TestScriptCopyer(object):
    @pytest.fixture
    def srcdir(self, tmpdir):
        return tmpdir.join('src').ensure(dir=True)

    @pytest.fixture
    def dstdir(self, tmpdir):
        return tmpdir.join('dst').ensure(dir=True)

    @pytest.fixture
    def copyer(self, srcdir, dstdir):
        from humpty import ScriptCopyer
        return ScriptCopyer(str(srcdir), str(dstdir))

    def test_copies_script(self, copyer, srcdir, dstdir):
        srcdir.join('tester').write(
            "#!python\n"
            "print('Hello')\n"
            )
        dstpath = dstdir.join('tester')

        scripts = copyer.make('tester')

        assert scripts == [str(dstpath)]
        result = dstdir.join('tester').open().read()
        # remove the blank line that distlib adds after the hashbang
        result_lines = list(filter(None, result.splitlines()))
        assert result_lines == [
            "#!%s" % sys.executable,
            "print('Hello')",
            ]

    def test_skips_wrapper(self, copyer, dstdir):
        scripts = copyer.make('tester = foo:main')
        assert scripts == []
        assert len(dstdir.listdir()) == 0
