import pytest

from stackinator.recipe import Recipe


def make_recipe(commit):
    """A Recipe with only the spack config populated, bypassing the heavy __init__."""
    recipe = Recipe.__new__(Recipe)
    recipe._config = {"spack": {"commit": commit}}
    return recipe


@pytest.mark.parametrize(
    "commit, expected",
    [
        # release branches and tags pin the major.minor version
        ("releases/v1.0", "1.0"),
        ("releases/v1.1", "1.1"),
        ("releases/v2.0", "2.0"),
        ("v1.0.0", "1.0"),
        ("v1.1.3", "1.1"),
        ("1.0", "1.0"),
        # the version cannot be determined -> default to the latest supported (1.1)
        ("develop", "1.1"),
        ("main", "1.1"),
        (None, "1.1"),
        ("a3f9c1e8b2d4f6a7c9e1b3d5f7a9c1e3b5d7f9a1", "1.1"),
    ],
)
def test_find_spack_version(commit, expected):
    """find_spack_version infers major.minor from the commit, defaulting to 1.1."""
    recipe = make_recipe(commit)
    assert recipe.find_spack_version(develop=False) == expected


def test_find_spack_version_develop_flag():
    """The --develop flag forces the latest supported version regardless of commit."""
    recipe = make_recipe("releases/v1.0")
    assert recipe.find_spack_version(develop=True) == "1.1"
