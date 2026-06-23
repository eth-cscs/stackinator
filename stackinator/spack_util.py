import re
from typing import NamedTuple, Optional


class Version(NamedTuple):
    """A minimal "major.minor" spack version that supports comparison.

    Implemented as a NamedTuple so that the comparison operators (==, <, >=, ...)
    come for free via tuple ordering, e.g. ``Version(1, 2) > Version(1, 1)``.
    Because it is a tuple it also compares directly against plain tuples, which is
    convenient in Jinja templates: ``{% if spack_version >= (1, 2) %}``.
    """

    major: int
    minor: int

    @classmethod
    def parse(cls, text: str) -> Optional["Version"]:
        """Extract a "major.minor" Version from text, or None if none is present.

        Matches a release branch/tag (releases/v1.0, v1.1, v1.1.2) or a bare
        "1.0", ignoring any trailing patch component.
        """
        match = re.search(r"v?(\d+)\.(\d+)(?:\.\d+)?", text)
        if match is None:
            return None
        return cls(int(match.group(1)), int(match.group(2)))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}"


def is_repo(path):
    """
    Returns True if path contains a spack package repo, where the definition of
    a spack package repo is a directory with a sub-directory named packages

    Otherwise returns False.
    """
    pkg_path = path / "packages"
    if pkg_path.exists() and pkg_path.is_dir():
        return True
    return False
