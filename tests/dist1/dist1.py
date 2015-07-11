# -*- coding: utf-8 -*-
import sys


def main():
    sys.exit(42)


def test_is_compiled():
    global __cached__, __file__
    try:
        source = __cached__ or __file__
    except NameError:
        source = __file__
    assert source.endswith('.pyc')


def test_extras():
    from extension_dist.test_ext import get_the_answer

    assert get_the_answer() == 42


def test_no_extras():
    try:
        import extension_dist   # noqa
    except ImportError:
        pass
    else:
        assert False, "extra was insatlled when it shouldn't have been"
