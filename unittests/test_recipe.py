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
            "intel-oneapi-compilers": {"version": "2024.1", "spec": None},
        }
    )
    assert recipe.compilers["gcc"]["specs"] == ["gcc@13 +bootstrap"]
    assert recipe.compilers["nvhpc"]["specs"] == ["nvhpc@25.1 ~mpi~blas~lapack"]
    assert recipe.compilers["llvm"]["specs"] == ["llvm@16 +clang ~gold"]
    assert recipe.compilers["llvm-amdgpu"]["specs"] == ["llvm-amdgpu@6.0"]
    assert recipe.compilers["intel-oneapi-compilers"]["specs"] == ["intel-oneapi-compilers@2024.1"]
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
