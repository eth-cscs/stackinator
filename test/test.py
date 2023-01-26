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
    print(f'=== running yaml schema tests in {test_path}')

    print()
    print(f'=== config.yaml')
    for yaml_file in ['config1.yaml', 'config2.yaml']:
        with open(yaml_path / yaml_file) as fid:
            print(f'====== {yaml_file} ======')
            raw = yaml.load(fid, Loader=yaml.Loader)
            print(raw)
            schema.validator(schema.config_schema).validate(raw)
            print(raw)

    print()
    print(f'=== compilers.yaml')
    for yaml_file in ['compilers1.yaml']:
        with open(yaml_path / yaml_file) as fid:
            print(f'====== {yaml_file} ======')
            raw = yaml.load(fid, Loader=yaml.Loader)
            print(raw)
            schema.validator(schema.compilers_schema).validate(raw)
            print(raw)
