#!/usr/bin/env python3

import pathlib
import sys

prefix = os.path.abspath(os.path.dirname(__file__))
external = os.path.join(prefix, 'external')
sys.path = [prefix, external] + sys.path

if __name__ == '__main__':
    sys.argv = [sys.argv[0], 'test']
    sys.exit(pytest.main())
