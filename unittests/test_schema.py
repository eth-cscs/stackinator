#!/usr/bin/python3

import pathlib

import jsonschema
import pytest
import yaml

import stackinator.schema as schema


@pytest.fixture
def test_path():
    return pathlib.Path(__file__).parent.resolve()


@pytest.fixture
def yaml_path(test_path):
    return test_path / "yaml"


@pytest.fixture
def recipes():
    return [
        "host-recipe",
        "base-nvgpu",
        "cache",
        "with-repo",
    ]


@pytest.fixture
def recipe_paths(test_path, recipes):
    return [test_path / "recipes" / r for r in recipes]


def test_config_yaml(yaml_path):
    # test that the defaults are set as expected
    with open(yaml_path / "config.defaults.yaml") as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.validate(schema.ConfigValidator, raw)
        assert raw["store"] == "/user-environment"
        assert raw["spack"]["commit"] is None
        assert raw["modules"] == True  # noqa: E712
        assert raw["mirror"] == {"enable": True, "key": None}
        assert raw["description"] is None

    with open(yaml_path / "config.full.yaml") as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.validate(schema.ConfigValidator, raw)
        assert raw["store"] == "/alternative-point"
        assert raw["spack"]["commit"] == "6408b51"
        assert raw["modules"] == False  # noqa: E712
        assert raw["mirror"] == {"enable": True, "key": "/home/bob/veryprivate.key"}
        assert raw["description"] == "a really useful environment"


def test_recipe_config_yaml(recipe_paths):
    # validate the config.yaml in the test recipes
    for p in recipe_paths:
        with open(p / "config.yaml") as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            schema.validate(schema.ConfigValidator, raw)


def test_compilers_yaml(yaml_path):
    # test that the defaults are set as expected
    with open(yaml_path / "compilers.defaults.yaml") as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.validate(schema.CompilersValidator, raw)
        assert raw["gcc"] == {"version": "10.2"}
        assert raw["llvm"] is None

    with open(yaml_path / "compilers.full.yaml") as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.validate(schema.CompilersValidator, raw)
        assert raw["gcc"] == {"version": "11"}
        assert raw["llvm"] == {"version": "13"}
        assert raw["nvhpc"] == {"version": "25.1"}


def test_recipe_compilers_yaml(recipe_paths):
    # validate the compilers.yaml in the test recipes
    for p in recipe_paths:
        with open(p / "compilers.yaml") as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            schema.validate(schema.CompilersValidator, raw)


def test_environments_yaml(yaml_path):
    with open(yaml_path / "environments.full.yaml") as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.validate(schema.EnvironmentsValidator, raw)

        # the defaults-env does not set fields
        # test that they have been set to the defaults correctly

        assert "defaults-env" in raw
        env = raw["defaults-env"]

        # test the required fields were read correctly
        assert env["compiler"] == ["gcc"]
        assert env["specs"] == ["tree"]

        # test defaults were set correctly
        assert env["unify"] == True  # noqa: E712
        assert env["packages"] == []
        assert env["variants"] == []
        assert env["mpi"] is None
        assert env["views"] == {}

        env = raw["defaults-env-mpi-nogpu"]
        assert env["mpi"]["spec"] is not None
        assert env["mpi"]["gpu"] is None

        # the full-env sets all of the fields
        # test that they have been read correctly

        assert "full-env" in raw
        env = raw["full-env"]
        assert env["compiler"] == ["gcc"]
        assert env["specs"] == ["osu-micro-benchmarks@5.9", "hdf5 +mpi"]

        # test defaults were set correctly
        assert env["unify"] == "when_possible"
        assert env["packages"] == ["perl", "git"]
        assert env["mpi"] == {"spec": "cray-mpich", "gpu": "cuda"}
        assert env["variants"] == ["+mpi", "+cuda"]
        assert env["views"] == {"default": None}

    # check that only allowed fields are accepted
    # from an example that was silently validated
    with open(yaml_path / "environments.err-providers.yaml") as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        with pytest.raises(
            jsonschema.exceptions.ValidationError,
            match=r"Additional properties are not allowed \('providers' was unexpected",
        ):
            schema.validate(schema.EnvironmentsValidator, raw)


def test_recipe_environments_yaml(recipe_paths):
    # validate the environments.yaml in the test recipes
    for p in recipe_paths:
        with open(p / "environments.yaml") as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            schema.validate(schema.EnvironmentsValidator, raw)
