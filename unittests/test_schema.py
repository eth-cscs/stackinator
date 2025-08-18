#!/usr/bin/python3

import pathlib
from textwrap import dedent

import jsonschema
import pytest
import pprint
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
        schema.ConfigValidator.validate(raw)
        assert raw["store"] == "/user-environment"
        assert raw["spack"]["commit"] is None
        assert raw["spack"]["packages"]["commit"] is None
        assert raw["modules"] == True  # noqa: E712
        assert raw["mirror"] == {"enable": True, "key": None}
        assert raw["description"] is None

    # no spack:commit
    config = dedent("""
    version: 2
    name: env-without-spack-commit
    spack:
        repo: https://github.com/spack/spack.git
        packages:
            repo: https://github.com/spack/spack.git
            commit: develop-packages
    """)
    raw = yaml.load(
        config,
        Loader=yaml.Loader,
    )
    schema.ConfigValidator.validate(raw)
    assert raw["spack"]["commit"] is None
    assert raw["spack"]["packages"]["commit"] is not None
    assert raw["modules"] == True  # noqa: E712
    assert raw["mirror"] == {"enable": True, "key": None}
    assert raw["description"] is None

    # no spack:packages:commit
    config = dedent("""
    version: 2
    name: env-without-spack-packages-commit
    spack:
        repo: https://github.com/spack/spack.git
        commit: develop
        packages:
            repo: https://github.com/spack/spack.git
    """)
    raw = yaml.load(
        config,
        Loader=yaml.Loader,
    )
    schema.ConfigValidator.validate(raw)
    assert raw["spack"]["commit"] == "develop"
    assert raw["spack"]["packages"]["commit"] is None
    assert raw["modules"] == True  # noqa: E712
    assert raw["mirror"] == {"enable": True, "key": None}
    assert raw["description"] is None

    # full config
    with open(yaml_path / "config.full.yaml") as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.ConfigValidator.validate(raw)
        assert raw["store"] == "/alternative-point"
        assert raw["spack"]["commit"] == "6408b51"
        assert raw["spack"]["packages"]["commit"] == "v2025.07.0"
        assert raw["modules"] == False  # noqa: E712
        assert raw["mirror"] == {"enable": True, "key": "/home/bob/veryprivate.key"}
        assert raw["description"] == "a really useful environment"

    # unsupported old version
    with pytest.raises(RuntimeError, match="incompatible uenv recipe version"):
        config = dedent("""
        name: cuda-env
        spack:
            repo: https://github.com/spack/spack.git
        """)
        raw = yaml.load(config, Loader=yaml.Loader)
        schema.ConfigValidator.validate(raw)


def test_recipe_config_yaml(recipe_paths):
    # validate the config.yaml in the test recipes
    for p in recipe_paths:
        with open(p / "config.yaml") as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            schema.ConfigValidator.validate(raw)


def test_compilers_yaml(yaml_path):
    # test that the defaults are set as expected
    with open(yaml_path / "compilers.defaults.yaml") as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.CompilersValidator.validate(raw)
        assert raw["gcc"] == {"version": "10.2"}
        assert raw["llvm"] is None

    with open(yaml_path / "compilers.full.yaml") as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.CompilersValidator.validate(raw)
        assert raw["gcc"] == {"version": "11"}
        assert raw["llvm"] == {"version": "13"}
        assert raw["nvhpc"] == {"version": "25.1"}


def test_recipe_compilers_yaml(recipe_paths):
    # validate the compilers.yaml in the test recipes
    for p in recipe_paths:
        with open(p / "compilers.yaml") as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            schema.CompilersValidator.validate(raw)


def test_environments_yaml(yaml_path):
    with open(yaml_path / "environments.full.yaml") as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.EnvironmentsValidator.validate(raw)

        print("===========================================================================")
        pprint.pp(raw)
        print("===========================================================================")

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
        assert env["network"] == {"mpi": None, "specs": None}
        assert env["views"] == {}

        env = raw["defaults-env-mpi-nogpu"]
        assert env["network"]["mpi"] == "cray-mpich"

        # the full-env sets all of the fields
        # test that they have been read correctly

        assert "full-env" in raw
        env = raw["full-env"]
        assert env["compiler"] == ["gcc"]
        assert env["specs"] == ["osu-micro-benchmarks@5.9", "hdf5 +mpi"]
        assert env["network"] == {"mpi": "cray-mpich +cuda", "specs": ["libfabric@2.2.0"]}

        # test defaults were set correctly
        assert env["unify"] == "when_possible"
        assert env["packages"] == ["perl", "git"]
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
            schema.EnvironmentsValidator.validate(raw)


def test_recipe_environments_yaml(recipe_paths):
    # validate the environments.yaml in the test recipes
    for p in recipe_paths:
        with open(p / "environments.yaml") as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            schema.EnvironmentsValidator.validate(raw)
