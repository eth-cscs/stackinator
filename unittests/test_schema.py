#!/usr/bin/env python3

import pathlib
from textwrap import dedent

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


@pytest.fixture(params=["host-recipe", "base-nvgpu", "cache", "with-repo", "with-multi-repos"])
def recipe(request):
    return request.param


@pytest.fixture
def recipe_path(test_path, recipe):
    return test_path / "recipes" / recipe


def test_config_yaml(yaml_path):
    # test that the defaults are set as expected
    with open(yaml_path / "config.defaults.yaml") as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.ConfigValidator.validate(raw)
        assert raw["store"] == "/user-environment"
        assert raw["spack"]["commit"] is None
        assert raw["description"] is None

    # single repo format with packages commit
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
    assert raw["spack"]["packages"]["commit"] == "develop-packages"
    assert raw["description"] is None

    # single repo format missing packages commit should fail
    with pytest.raises(Exception):
        config = dedent("""
        version: 2
        name: env-no-pkg-commit
        spack:
            repo: https://github.com/spack/spack.git
            commit: develop
            packages:
                repo: https://github.com/spack/spack.git
        """)
        raw = yaml.load(config, Loader=yaml.Loader)
        schema.ConfigValidator.validate(raw)

    # full config
    with open(yaml_path / "config.full.yaml") as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.ConfigValidator.validate(raw)
        assert raw["store"] == "/alternative-point"
        assert raw["spack"]["commit"] == "6408b51"
        assert raw["spack"]["packages"]["commit"] == "v2025.07.0"
        assert raw["modules"] == False  # noqa: E712
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

    # map format: single entry
    config = dedent("""
    version: 2
    name: map-single
    spack:
        repo: https://github.com/spack/spack.git
        packages:
            my-packages:
                repo: https://github.com/example/spack-packages.git
                commit: v1.0
    """)
    raw = yaml.load(config, Loader=yaml.Loader)
    schema.ConfigValidator.validate(raw)
    assert "my-packages" in raw["spack"]["packages"]
    assert raw["spack"]["packages"]["my-packages"]["repo"] == "https://github.com/example/spack-packages.git"
    assert raw["spack"]["packages"]["my-packages"]["commit"] == "v1.0"

    # map format: multiple entries with commits
    config = dedent("""
    version: 2
    name: map-multi
    spack:
        repo: https://github.com/spack/spack.git
        packages:
            my-packages:
                repo: https://github.com/example/spack-packages.git
                commit: v1.0
            other-packages:
                repo: https://github.com/example/other-packages.git
                commit: v2.0
    """)
    raw = yaml.load(config, Loader=yaml.Loader)
    schema.ConfigValidator.validate(raw)
    assert raw["spack"]["packages"]["my-packages"]["commit"] == "v1.0"
    assert raw["spack"]["packages"]["other-packages"]["commit"] == "v2.0"

    # map format: empty map should fail
    with pytest.raises(Exception):
        config = dedent("""
        version: 2
        name: map-empty
        spack:
            repo: https://github.com/spack/spack.git
            packages: {}
        """)
        raw = yaml.load(config, Loader=yaml.Loader)
        schema.ConfigValidator.validate(raw)

    # map format: entry missing repo should fail
    with pytest.raises(Exception):
        config = dedent("""
        version: 2
        name: map-no-repo
        spack:
            repo: https://github.com/spack/spack.git
            packages:
                my-packages:
                    commit: v1.0
        """)
        raw = yaml.load(config, Loader=yaml.Loader)
        schema.ConfigValidator.validate(raw)

    # map format: custom path
    config = dedent("""
    version: 2
    name: map-custom-path
    spack:
        repo: https://github.com/spack/spack.git
        packages:
            my-packages:
                repo: https://github.com/example/spack-packages.git
                commit: v1.0
                path: custom/repo/location
    """)
    raw = yaml.load(config, Loader=yaml.Loader)
    schema.ConfigValidator.validate(raw)
    assert raw["spack"]["packages"]["my-packages"]["path"] == "custom/repo/location"

    # map format: no path (default behavior)
    config = dedent("""
    version: 2
    name: map-no-path
    spack:
        repo: https://github.com/spack/spack.git
        packages:
            my-packages:
                repo: https://github.com/example/spack-packages.git
                commit: v2.0
    """)
    raw = yaml.load(config, Loader=yaml.Loader)
    schema.ConfigValidator.validate(raw)
    assert "path" not in raw["spack"]["packages"]["my-packages"]


def test_recipe_config_yaml(recipe_path):
    # validate the config.yaml in the test recipes
    with open(recipe_path / "config.yaml") as fid:
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


def test_recipe_compilers_yaml(recipe_path):
    # validate the compilers.yaml in the test recipes
    with open(recipe_path / "compilers.yaml") as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.CompilersValidator.validate(raw)


def test_environments_yaml(yaml_path):
    with open(yaml_path / "environments.full.yaml") as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.EnvironmentsValidator.validate(raw)

        # the defaults-env does not set fields
        # test that they have been set to the defaults correctly

        assert "defaults-env" in raw
        env = raw["defaults-env"]

        # test the required fields were read correctly
        assert env["compiler"] == ["gcc"]
        assert env["specs"] == ["tree"]

        # test defaults were set correctly
        assert env["unify"] == True  # noqa: E712
        assert env["duplicates"]["strategy"] == "minimal"
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
        assert env["duplicates"]["strategy"] == "full"
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


def test_recipe_environments_yaml(recipe_path):
    # validate the environments.yaml in the test recipes
    with open(recipe_path / "environments.yaml") as fid:
        raw = yaml.load(fid, Loader=yaml.Loader)
        schema.EnvironmentsValidator.validate(raw)


@pytest.mark.parametrize(
    "recipe",
    [
        dedent(
            """
            modules: {}
            """
        ),
        dedent(
            """
            modules:
              default:
                arch_folder: false
            """
        ),
        dedent(
            """
            modules:
              # Paths tomodules: check when creating modules for all module sets
              prefix_insmodules:pections:
                bin:
                  - PATH
                lib:
                  - LD_LIBRARY_PATH
                lib64:
                  - LD_LIBRARY_PATH

              default:
                arch_folder: false
                # Where to install modules
                tcl:
                  all:
                    autoload: none
                  hash_length: 0
                  exclude_implicits: true
                  exclude: []
                  projections:
                    all: '{name}/{version}'
            """
        ),
        dedent(
            """
            modules:
              default:
                roots:
                  tcl: /path/which/is/going/to/be/ignored
            """
        ),
    ],
)
def test_valid_modules_yaml(recipe):
    instance = yaml.load(recipe, Loader=yaml.Loader)
    schema.ModulesValidator.validate(instance)
    assert not instance["modules"]["default"]["arch_folder"]


@pytest.mark.parametrize(
    "recipe",
    [
        dedent(
            """
            modules:
              default:
                arch_folder: true
            """
        ),
    ],
)
def test_invalid_modules_yaml(recipe):
    with pytest.raises(Exception):
        schema.ModulesValidator.validate(yaml.load(recipe, Loader=yaml.Loader))
