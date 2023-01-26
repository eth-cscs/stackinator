#!/usr/bin/python3

import pathlib
import sys
import yaml

test_path = pathlib.Path(__file__).parent.resolve()
yaml_path = test_path / 'yaml'
prefix = pathlib.Path(__file__).parent.parent.resolve()
external = prefix / 'external'
sys.path = [prefix.as_posix(), external.as_posix()] + sys.path

import sstool.schema as schema

# Once we've set up the system path, run the tool's main method
if __name__ == "__main__":
    print(f'running yaml schema tests in {test_path}')
    with open(yaml_path / 'config1.yaml') as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        print('=== before ===')
        print(raw)
        schema.validator(schema.config_schema).validate(raw)
        print('=== after ===')
        print(raw)
