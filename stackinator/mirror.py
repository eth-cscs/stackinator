import os
import pathlib
import urllib.request

import yaml

from . import schema


def configuration_from_file(file):
    with file.open() as fid:
        # load the raw yaml input
        raw = yaml.load(fid, Loader=yaml.Loader)

        # validate the yaml
        schema.CacheValidator.validate(raw)

        mirrors = [mirror for mirror in raw if mirror["enabled"]]

        for mirror in mirrors:
            url = mirror["url"]
            if url.beginswith("file://"):
                # verify that the root path exists
                path = pathlib.Path(os.path.expandvars(url))
                if not path.is_absolute():
                    raise FileNotFoundError(f"The build cache path '{path}' is not absolute")
                if not path.is_dir():
                    raise FileNotFoundError(f"The build cache path '{path}' does not exist")

                mirror["url"] = path

            else:
                try:
                    request = urllib.request.Request(url, method='HEAD')
                    response = urllib.request.urlopen(request)
                except urllib.error.URLError as e:
                    print(f'Error: {e.reason}')

        return mirrors


def generate_mirrors_yaml(config):
    path = config["path"].as_posix()
    mirrors = {
        "mirrors": {
            "alpscache": {
                "fetch": {
                    "url": f"file://{path}",
                },
                "push": {
                    "url": f"file://{path}",
                },
            }
        }
    }

    return yaml.dump(mirrors, default_flow_style=False)
