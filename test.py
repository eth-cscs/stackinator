#!/usr/bin/env python3

import pathlib
import sys

prefix = pathlib.Path(__file__).parent.resolve()
external = prefix / 'external'
sys.path = [prefix.as_posix(), external.as_posix()] + sys.path

import pytest

if __name__ == '__main__':
    sys.argv = [sys.argv[0], '-vv', 'test']
    sys.exit(pytest.main())
