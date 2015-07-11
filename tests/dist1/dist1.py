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
