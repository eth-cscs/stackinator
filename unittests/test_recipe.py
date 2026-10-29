import logging

import pytest

from stackinator.recipe import Recipe
from stackinator.spack_util import Version


def make_recipe(commit=None):
    """A Recipe with only the spack config populated, bypassing the heavy __init__."""
    recipe = Recipe.__new__(Recipe)
    recipe._config = {"spack": {"commit": commit}}
    recipe._logger = logging.getLogger("test_recipe")
    return recipe


@pytest.mark.parametrize(
    "commit, expected",
    [
        # release branches and tags pin the major.minor version
        ("releases/v1.0", Version(1, 0)),
        ("releases/v1.1", Version(1, 1)),
        ("releases/v2.0", Version(2, 0)),
        ("v1.0.0", Version(1, 0)),
        ("v1.1.3", Version(1, 1)),
        ("1.0", Version(1, 0)),
        # the develop and main branches of spack are now at 1.2
        ("develop", Version(1, 2)),
        ("main", Version(1, 2)),
        (None, Version(1, 2)),
        # an unrecognised commit -> default to the most recent expected version (1.1)
        ("a3f9c1e8b2d4f6a7c9e1b3d5f7a9c1e3b5d7f9a1", Version(1, 1)),
    ],
)
def test_find_spack_version(commit, expected):
    """find_spack_version infers a Version from the commit, defaulting to 1.1."""
    recipe = make_recipe(commit)
    assert recipe.find_spack_version(develop=False) == expected


def test_find_spack_version_develop_flag():
    """The --develop flag targets the develop branch of spack, now at 1.2."""
    recipe = make_recipe("releases/v1.0")
    assert recipe.find_spack_version(develop=True) == Version(1, 2)


def test_generate_compiler_specs_defaults():
    """Without a 'spec' field, each compiler gets its default variants."""
    recipe = make_recipe()
    recipe.generate_compiler_specs(
        {
            "gcc": {"version": "13", "spec": None},
            "nvhpc": {"version": "25.1", "spec": None},
            "llvm": {"version": "16", "spec": None},
            "llvm-amdgpu": {"version": "6.0", "spec": None},
            "intel-oneapi": {"version": "2024.1", "spec": None},
            "intel-classic": {"version": "2021.10.0", "spec": None},
        }
    )
    assert recipe.compilers["gcc"]["specs"] == ["gcc@13 +bootstrap"]
    assert recipe.compilers["nvhpc"]["specs"] == ["nvhpc@25.1 ~mpi~blas~lapack"]
    assert recipe.compilers["llvm"]["specs"] == ["llvm@16 +clang ~gold"]
    assert recipe.compilers["llvm-amdgpu"]["specs"] == ["llvm-amdgpu@6.0"]
    # the recipe key differs from the spack package name for the intel compilers
    assert recipe.compilers["intel-oneapi"]["specs"] == ["intel-oneapi-compilers@2024.1"]
    assert recipe.compilers["intel-oneapi"]["package"] == "intel-oneapi-compilers"
    assert recipe.compilers["intel-classic"]["specs"] == ["intel-oneapi-compilers-classic@2021.10.0"]
    assert recipe.compilers["intel-classic"]["package"] == "intel-oneapi-compilers-classic"
    assert not recipe.use_system_gcc


def test_generate_compiler_specs_custom_spec():
    """A 'spec' field replaces the default variants for that compiler."""
    recipe = make_recipe()
    recipe.generate_compiler_specs(
        {
            "gcc": {"version": "13", "spec": "~bootstrap+nvptx"},
            "nvhpc": {"version": "25.1", "spec": None},
            "llvm": {"version": "16", "spec": "+clang +flang ~gold"},
        }
    )
    assert recipe.compilers["gcc"]["specs"] == ["gcc@13 ~bootstrap+nvptx"]
    # nvhpc keeps the default variants
    assert recipe.compilers["nvhpc"]["specs"] == ["nvhpc@25.1 ~mpi~blas~lapack"]
    assert recipe.compilers["llvm"]["specs"] == ["llvm@16 +clang +flang ~gold"]


def test_generate_compiler_specs_system_gcc():
    """A custom spec is ignored when the system gcc is used."""
    recipe = make_recipe()
    recipe.generate_compiler_specs({"gcc": {"version": "system", "spec": "+nvptx"}})
    assert recipe.compilers["gcc"] == {"system": True}
    assert recipe.use_system_gcc


def _env(compilers, add_compilers):
    return {"compiler": compilers, "views": [{"extra": {"add_compilers": add_compilers}}], "specs": []}


def test_compiler_module_specs_built_compiler():
    """A built compiler is made explicit instead, so it needs no include entry."""
    recipe = make_recipe()
    recipe.generate_compiler_specs({"gcc": {"version": "14", "spec": None}})
    recipe.environments = {"a": _env(["gcc"], True)}
    assert recipe.compiler_module_specs == []


def test_compiler_module_specs_system_gcc():
    """The system gcc is an external, so it needs an include entry to get a module."""
    recipe = make_recipe()
    recipe.generate_compiler_specs({"gcc": {"version": "system", "spec": None}})
    recipe.environments = {"a": _env(["gcc"], True)}
    assert recipe.compiler_module_specs == ["gcc"]


def test_compiler_module_specs_not_exposed():
    """A compiler no view exposes gets no module, system or not."""
    recipe = make_recipe()
    recipe.generate_compiler_specs({"gcc": {"version": "system", "spec": None}})
    recipe.environments = {"a": _env(["gcc"], False)}
    assert recipe.compiler_module_specs == []
    assert recipe.provided_compilers == set()


def test_provided_compilers():
    """A compiler is provided when a view with add_compilers exposes it."""
    recipe = make_recipe()
    recipe.generate_compiler_specs({"gcc": {"version": "14", "spec": None}, "nvhpc": {"version": "25.1", "spec": None}})
    recipe.environments = {"a": _env(["gcc"], True), "b": _env(["nvhpc"], False)}
    assert recipe.provided_compilers == {"gcc"}


def test_provided_compilers_excludes_system():
    """A system compiler is an external, so there is no group to mark explicit."""
    recipe = make_recipe()
    recipe.generate_compiler_specs(
        {"gcc": {"version": "system", "spec": None}, "llvm": {"version": "20", "spec": None}}
    )
    recipe.environments = {"a": _env(["llvm", "gcc"], True)}
    assert recipe.provided_compilers == {"llvm"}
    assert recipe.exposed_compilers == {"llvm", "gcc"}


def test_provided_compilers_no_views():
    """No view exposing compilers means none are provided."""
    recipe = make_recipe()
    recipe.generate_compiler_specs({"gcc": {"version": "14", "spec": None}})
    recipe.environments = {"a": {"compiler": ["gcc"], "views": [], "specs": []}}
    assert recipe.provided_compilers == set()
