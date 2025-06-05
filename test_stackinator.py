#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "jinja2",
#   "jsonschema",
#   "pytest",
#   "pyYAML",
# ]
# ///

import pathlib
import sys

prefix = pathlib.Path(__file__).parent.resolve()
sys.path = [prefix.as_posix()] + sys.path

import pytest  # noqa: E402

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "-vv", "unittests"]
    sys.exit(pytest.main())
