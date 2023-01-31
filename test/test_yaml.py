#!/usr/bin/python3

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
    # test that the defaults are set as expected
    with open(yaml_path / 'config.defaults.yaml') as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.validator(schema.config_schema).validate(raw)
        assert raw['store'] == '/user-environment'
        assert raw['spack']['commit'] == None
        assert raw['modules'] == True
        assert raw['mirror']['enable'] == True
        assert raw['mirror']['key'] == None

    with open(yaml_path / 'config.full.yaml') as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.validator(schema.config_schema).validate(raw)
        assert raw['store'] == '/alternative-point'
        assert raw['spack']['commit'] == '6408b51'
        assert raw['modules'] == False
        assert raw['mirror']['key'] == '/home/bob/veryprivate.key'
        assert raw['mirror']['enable'] == True

def test_compilers_yaml(yaml_path):
    # test that the defaults are set as expected
    with open(yaml_path / 'compilers.defaults.yaml') as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.validator(schema.compilers_schema).validate(raw)
        assert raw['bootstrap'] == {'spec': 'gcc@11'}
        assert raw['gcc'] == {'specs': ['gcc@10.2']}
        assert raw['llvm'] == None

    with open(yaml_path / 'compilers.full.yaml') as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.validator(schema.compilers_schema).validate(raw)
        assert raw['bootstrap']['spec'] == 'gcc@11'
        assert raw['gcc'] == {'specs': ['gcc@11', 'gcc@10.2', 'gcc@9.3.0']}
        assert raw['llvm'] == {
            'specs': ['llvm@13', 'llvm@11.2', 'nvhpc@22.11'],
            'requires': 'gcc@10.2'
        }


