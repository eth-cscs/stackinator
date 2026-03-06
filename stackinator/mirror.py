import os
import pathlib
import urllib.request
from typing import Optional

import yaml

from . import schema


def configuration_from_file(path: pathlib.Path, cmdline_cache: Optional[str] = None):
    """Configure mirrors from both the system 'mirror.yaml' file and the command line."""

    if path.exists():
        with path.open() as fid:
            # load the raw yaml input
            raw = yaml.load(fid, Loader=yaml.Loader)

        print(f"Configuring mirrors and buildcache from '{path}'")

        # validate the yaml
        schema.CacheValidator.validate(raw)

        mirrors = [mirror for mirror in raw if mirror["enabled"]]
    else:
        mirrors = []

    buildcache_dest_count = len([mirror for mirror in mirrors if mirror['buildcache']])
    if buildcache_dest_count > 1:
        raise RuntimeError("Mirror config has more than one mirror specified as the build cache destination "
                           "in the system config's 'mirrors.yaml'.")
    elif buildcache_dest_count == 1 and cmdline_cache:
        raise RuntimeError("Build cache destination specified on the command line and in the system config's "
                           "'mirrors.yaml'. It can be one or the other, but not both.")

    # Add or set the cache given on the command line as the buildcache destination
    if cmdline_cache is not None:
        existing_mirror = [mirror for mirror in mirrors if mirror['name'] == cmdline_cache][:1]
        # If the mirror name given on the command line isn't in the config, assume it 
        # is the URL to a build cache.
        if not existing_mirror:
            mirrors.append(
                {
                    'name': 'cmdline_cache',
                    'url': cmdline_cache,
                    'buildcache': True,
                    'bootstrap': False,
                }
            )

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


def generate_mirrors_yaml(mirrors):
    yaml = {"mirrors": {}}

    for m in mirrors:
        name = m["name"]
        url = m["url"]

        yaml["mirrors"][name] = {
            "fetch": {"url": url},
            "push": {"url": url},
        }

    return yaml.dump(yaml, default_flow_style=False)