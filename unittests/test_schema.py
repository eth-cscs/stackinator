#!/usr/bin/python3

import pathlib
import pytest
import yaml

import stackinator.schema as schema

@pytest.fixture
def test_path():
    return pathlib.Path(__file__).parent.resolve()

@pytest.fixture
def yaml_path(test_path):
    return test_path / 'yaml'

@pytest.fixture
def recipes():
    return ['host-recipe', 'base-amdgpu', 'base-nvgpu', 'cache', 'unique-bootstrap']

@pytest.fixture
def recipe_paths(test_path, recipes):
    return [test_path / 'recipes' / r for r in recipes]

def test_config_yaml(yaml_path):
    # test that the defaults are set as expected
    with open(yaml_path / 'config.defaults.yaml') as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.validator(schema.config_schema).validate(raw)
        assert raw['store'] == '/user-environment'
        assert raw['spack']['commit'] == None
        assert raw['modules'] == True
        assert raw['mirror'] == {'enable': True, 'key': None}

    with open(yaml_path / 'config.full.yaml') as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.validator(schema.config_schema).validate(raw)
        assert raw['store'] == '/alternative-point'
        assert raw['spack']['commit'] == '6408b51'
        assert raw['modules'] == False
        assert raw['mirror'] == {'enable': True, 'key': '/home/bob/veryprivate.key'}

def test_recipe_config_yaml(yaml_path, recipe_paths):
    # validate the config.yaml in the test recipes
    for p in recipe_paths:
        with open(p / 'config.yaml') as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            schema.validator(schema.config_schema).validate(raw)

def test_compilers_yaml(yaml_path, recipe_paths):
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

def test_recipe_compilers_yaml(yaml_path, recipe_paths):
    # validate the compilers.yaml in the test recipes
    for p in recipe_paths:
        with open(p / 'compilers.yaml') as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            schema.validator(schema.compilers_schema).validate(raw)

def test_environments_yaml(yaml_path):
    with open(yaml_path / 'environments.full.yaml') as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.validator(schema.environments_schema).validate(raw)

        # the defaults-env does not set fields
        # test that they have been set to the defaults correctly

        assert 'defaults-env' in raw
        env = raw['defaults-env']

        # test the required fields were read correctly
        assert env['compiler'] == [{'toolchain': 'gcc', 'spec': 'gcc@11'}]
        assert env['specs'] == ['tree']

        # test defaults were set correctly
        assert env['unify'] == True
        assert env['packages'] == []
        assert env['variants'] == []
        assert env['mpi'] == None

        # the full-env sets all of the fields
        # test that they have been read correctly

        assert 'full-env' in raw
        env = raw['full-env']
        assert env['compiler'] == [
                {'toolchain': 'gcc', 'spec': 'gcc@11'},
                {'toolchain': 'gcc', 'spec': 'gcc@12'}
        ]
        assert env['specs'] == ['osu-micro-benchmarks@5.9','hdf5 +mpi']

        # test defaults were set correctly
        assert env['unify'] == 'when_possible'
        assert env['packages'] == ['perl', 'git']
        assert env['mpi'] == {'spec': 'cray-mpich-binary', 'gpu': 'cuda'}
        assert env['variants'] == ['+mpi', '+cuda']

def test_recipe_environments_yaml(yaml_path, recipe_paths):
    # validate the environments.yaml in the test recipes
    for p in recipe_paths:
        with open(p / 'environments.yaml') as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            schema.validator(schema.environments_schema).validate(raw)
