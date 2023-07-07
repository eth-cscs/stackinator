import os
import pathlib

import yaml

from . import schema


def configuration_from_file(file, mount):
    with file.open() as fid:
        # load the raw yaml input
        raw = yaml.load(fid, Loader=yaml.Loader)

        # validate the yaml
        schema.cache_validator.validate(raw)

        # verify that the root path exists
        path = pathlib.Path(os.path.expandvars(raw["root"]))
        if not path.is_absolute():
            raise FileNotFoundError(f"The build cache path '{path}' is not absolute")
        if not path.is_dir():
            raise FileNotFoundError(f"The build cache path '{path}' does not exist")

        raw["root"] = path

        # Put the build cache in a sub-directory named after the mount point.
        # This avoids relocation issues.
        raw["path"] = pathlib.Path(path.as_posix() + mount.as_posix())

        # verify that the key file exists if it was specified
        key = raw["key"]
        if key is not None:
            key = pathlib.Path(os.path.expandvars(key))
            if not key.is_absolute():
                raise FileNotFoundError(f"The build cache key '{key}' is not absolute")
            if not key.is_file():
                raise FileNotFoundError(f"The build cache key '{key}' does not exist")
            raw["key"] = key

        return raw


def generate_mirrors_yaml(config):
    path = config["path"].as_posix()
    mirrors = {
        "mirrors": {
            "alpscache": {
                "fetch": {
                    "url": f"file://{path}",
                    "access_pair": [None, None],
                    "access_token": None,
                    "profile": None,
                    "endpoint_url": None,
                },
                "push": {
                    "url": f"file://{path}",
                    "access_pair": [None, None],
                    "access_token": None,
                    "profile": None,
                    "endpoint_url": None,
                },
            }
        }
    }

    return yaml.dump(mirrors, default_flow_style=False)
