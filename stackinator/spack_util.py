import pathlib

from . import root_logger

def is_repo(path):
    pkg_path = path / "packages"
    if pkg_path.exists() and pkg_path.is_dir():
        return True
    return False

