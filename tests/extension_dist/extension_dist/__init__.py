# -*- coding: utf-8 -*-
from __future__ import absolute_import

import sys
from .test_ext import get_the_answer, read_the_answer


def main():
    sys.exit(get_the_answer())


def answer_from_resource():
    sys.exit(read_the_answer())
