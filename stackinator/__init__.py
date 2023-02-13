import logging
import pathlib


root_logger = logging.getLogger('stackinator')

#: (major, minor, dev release) tuple
def get_version():
    import os

    parent_path = pathlib.Path(__file__).parent.parent.resolve()
    with open(parent_path / "VERSION") as version_file:
        return version_file.read().strip()

#: PEP440 canonical <major>.<minor>.<dev> string
stackinator_version = get_version()

stackinator_version_info = tuple(stackinator_version.split('.'))

__all__ = ["stackinator_version_info", "stackinator_version"]
__version__ = stackinator_version
