import os
import pathlib
import urllib.request
from typing import Optional
import magic

import yaml

from . import schema

class MirrorConfigError(RuntimeError):
    """Exception class for errors thrown by mirror configuration problems."""



def configuration_from_file(system_config_root: pathlib.Path, cmdline_cache: Optional[str] = None):
    """Configure mirrors from both the system 'mirror.yaml' file and the command line."""

    path = system_config_root/"mirrors.yaml"
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
                raise FileNotFoundError(f"The mirror path '{path}' is not absolute")
            if not path.is_dir():
                raise FileNotFoundError(f"The mirror path '{path}' does not exist")

            mirror["url"] = path

        elif url.beginswith("https://"):
            try:
                request = urllib.request.Request(url, method='HEAD')
                response = urllib.request.urlopen(request)
            except urllib.error.URLError as e:
                raise MirrorConfigError(
                    f"Could not reach the mirror url '{url}'. " 
                    f"Check the url listed in mirrors.yaml in system config. \n{e.reason}")

        if mirror["bootstrap"]:
            #make bootstrap dirs
            #bootstrap/<mirror name>/metadata.yaml

        return mirrors


def setup(mirrors, config_path):
    dst = config_path / "mirrors.yaml"
    self._logger.debug(f"generate the spack mirrors.yaml: {dst}")
    with dst.open("w") as fid:
        fid.write()
    yaml = {"mirrors": {}}

    for m in mirrors:
        name = m["name"]
        url = m["url"]

        yaml["mirrors"][name] = {
            "fetch": {"url": url},
            "push": {"url": url},
        }

    return yaml.dump(yaml, default_flow_style=False)

#called from builder
def key_setup(mirrors: List[Dict], system_config_path: pathlib.Path, key_store: pathlib.Path):
    for mirror in mirrors:
        if mirror["key"]:
            key = mirror["key"]
            # if path, check if abs path, if not, append sys config path in front and check again
            path = pathlib.Path(os.path.expandvars(key))
            if path.exists():
                if not path.is_absolute():
                    #try prepending system config path
                    path = system_config_path + path
                    if not.path.is_file()
                        raise FileNotFoundError(
                            f"The key path '{path}' is not a file. "
                            f"Check the key listed in mirrors.yaml in system config.")
                file_type = magic.from_file(path)
                if not file_type.startswith("OpenPGP Public Key"):
                    raise MirrorConfigError(
                        f"'{key}' is not a valid GPG key. "
                        f"Check the key listed in mirrors.yaml in system config.")
                # copy file to key store
                with file open:
                    data = key.read
                dest = mkdir(new_key_file)
                dest.write(data)
                # mirror["key"] = new_path
                
            else:            
                # if PGP key, convert to binary, ???, convert back
                # if key, save to file, change to path
            
    