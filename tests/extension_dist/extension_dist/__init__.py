# -*- coding: utf-8 -*-
from __future__ import absolute_import


def test_extension():
    from .test_ext import get_the_answer

    assert get_the_answer() == 42


def test_eager_resources():
    from .test_ext import read_the_answer

    assert read_the_answer() == 42
