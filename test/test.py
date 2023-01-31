#!/usr/bin/python3

#import sys
#prefix = pathlib.Path(__file__).parent.parent.resolve()
#external = prefix / 'external'
#sys.path = [prefix.as_posix(), external.as_posix()] + sys.path

import pathlib
import pytest
import yaml

import sstool.schema as schema

@pytest.fixture
def test_path():
    return pathlib.Path(__file__).parent.resolve()

@pytest.fixture
def yaml_path(test_path):
    return test_path / 'yaml'

def test_config_yaml(yaml_path):
    with open(yaml_path / 'config.default.yaml') as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.validator(schema.config_schema).validate(raw)
        assert raw['store'] == '/user-environment'
        assert raw['spack']['commit'] == None
        assert raw['modules'] == True
        assert raw['mirror']['enable'] == True

#if __name__ == "__main__":
#    print(f'=== running yaml schema tests in {test_path}')
#
#    print()
#    print(f'=== config.yaml')
#    for yaml_file in ['config1.yaml', 'config2.yaml']:
#        with open(yaml_path / yaml_file) as fid:
#            print(f'====== {yaml_file} ======')
#            raw = yaml.load(fid, Loader=yaml.Loader)
#            print(raw)
#            schema.validator(schema.config_schema).validate(raw)
#            print(raw)
#
#    print()
#    print(f'=== compilers.yaml')
#    for yaml_file in ['compilers1.yaml']:
#        with open(yaml_path / yaml_file) as fid:
#            print(f'====== {yaml_file} ======')
#            raw = yaml.load(fid, Loader=yaml.Loader)
#            print(raw)
#            schema.validator(schema.compilers_schema).validate(raw)
#            print(raw)
