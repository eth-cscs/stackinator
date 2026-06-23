import pytest

from stackinator.recipe import Recipe
from stackinator.spack_util import Version


def make_recipe(commit):
    """A Recipe with only the spack config populated, bypassing the heavy __init__."""
    recipe = Recipe.__new__(Recipe)
    recipe._config = {"spack": {"commit": commit}}
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
