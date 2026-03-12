import os
import pathlib
import urllib.request
import urllib.error
from typing import ByteString, Optional, List, Dict
import magic

import yaml

from . import schema

class MirrorError(RuntimeError):
    """Exception class for errors thrown by mirror configuration problems."""

class Mirrors:
    """Manage the definition of mirrors in a recipe."""

    def __init__(self, system_config_root: pathlib.Path, cmdline_cache: Optional[str] = None):
        """Configure mirrors from both the system 'mirror.yaml' file and the command line."""

        self._system_config_root = system_config_root

        self.mirrors = self._load_mirrors(cmdline_cache)
        self._check_mirrors()
 
        self.build_cache_mirror = ([mirror for mirror in self.mirrors if mirror.get('buildcache', False)] 
                                   + [None]).pop(0)
        self.bootstrap_mirrors = [mirror for mirror in self.mirrors if mirror.get('bootstrap', False)]
        self.keys = [mirror['key'] for mirror in self.mirrors if mirror.get('key') is not None]

    def _load_mirrors(self, cmdline_cache: Optional[str]) -> List[Dict]:
        """Load the mirrors file, if one exists."""
        path = self._system_config_root/"mirrors.yaml"
        if path.exists():
            with path.open() as fid:
                # load the raw yaml input
                raw = yaml.load(fid, Loader=yaml.Loader)

            # validate the yaml
            schema.CacheValidator.validate(raw)

            mirrors = [mirror for mirror in raw if mirror["enabled"]]
        else:
            mirrors = []

        buildcache_dest_count = len([mirror for mirror in mirrors if mirror['buildcache']])
        if buildcache_dest_count > 1:
            raise MirrorError("Mirror config has more than one mirror specified as the build cache destination "
                               "in the system config's 'mirrors.yaml'.")
        elif buildcache_dest_count == 1 and cmdline_cache:
            raise MirrorError("Build cache destination specified on the command line and in the system config's "
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

        return mirrors

    def _check_mirrors(self):
        """Validate the mirror config entries."""

        for mirror in self.mirrors:
            url = mirror["url"]
            if url.beginswith("file://"):
                # verify that the root path exists
                path = pathlib.Path(os.path.expandvars(url))
                if not path.is_absolute():
                    raise MirrorError(f"The mirror path '{path}' is not absolute")
                if not path.is_dir():
                    raise MirrorError(f"The mirror path '{path}' is not a directory")

                mirror["url"] = path

            elif url.beginswith("https://"):
                try:
                    request = urllib.request.Request(url, method='HEAD')
                    urllib.request.urlopen(request)
                except urllib.error.URLError as e:
                    raise MirrorError(
                        f"Could not reach the mirror url '{url}'. " 
                        f"Check the url listed in mirrors.yaml in system config. \n{e.reason}")

    def create_spack_mirrors_yaml(self, dest: pathlib.Path):
        """Generate the mirrors.yaml for our build directory."""

        raw = {"mirrors": {}}

        for m in self.mirrors:
            name = m["name"]
            url = m["url"]

            raw["mirrors"][name] = {
                "fetch": {"url": url},
                "push": {"url": url},
            }

        with dest.open("w") as file:
            yaml.dump(raw, file, default_flow_style=False)

    def create_bootstrap_configs(self, config_root: pathlib.Path):
        """Create the bootstrap.yaml and bootstrap metadata dirs in our build dir."""

        if not self.bootstrap_mirrors:
            return
        
        bootstrap_yaml = {
            'sources': [],
            'trusted': {},
        }

        for mirror in self.bootstrap_mirrors:
            name = mirror['name']
            bs_mirror_path = config_root/f'bootstrap/{name}'
            # Tell spack where to find the metadata for each bootstrap mirror.
            bootstrap_yaml['sources'].append(
                {
                    'name': name,
                    'metadata': bs_mirror_path,
                }
            )
            # And trust each one
            bootstrap_yaml['trusted'][name] = True

            # Create the metadata dir and metadata.yaml
            bs_mirror_path.mkdir(parents=True)
            bs_mirror_yaml = {
                'type': 'install',
                'info': mirror['url'],
            }
            with (bs_mirror_path/'metadata.yaml').open('w') as file:
                yaml.dump(bs_mirror_yaml, file, default_flow_style=False)
        
        with (config_root/'bootstrap.yaml').open('w') as file:
            yaml.dump(bootstrap_yaml, file, default_flow_style=False)

    def key_setup(self, config_root: pathlib.Path):
        """Validate mirror keys, relocate to key_store, and update mirror config with new key paths."""

        for mirror in self.mirrors:
            if mirror["key"]:
                key = mirror["key"]

                # key will be saved under key_store/mirror_name.gpg
                dest = (key_store / f"'{mirror["name"]}'.gpg").resolve()

                # if path, check if abs path, if not, append sys config path in front and check again
                path = pathlib.Path(os.path.expandvars(key))
                if path.exists():
                    if not path.is_absolute():
                        #try prepending system config path
                        path = self._system_config_root/path
                        if not path.is_file():
                            raise MirrorError(
                                f"The key path '{path}' is not a file. "
                                f"Check the key listed in mirrors.yaml in system config.")

                    file_type = magic.from_file(path)

                    if not file_type.startswith("OpenPGP Public Key"):
                        raise MirrorError(
                            f"'{path}' is not a valid GPG key. "
                            f"Check the key listed in mirrors.yaml in system config.")
                    
                    # copy key to new destination in key store
                    with open(path, 'r') as reader, open(dest, 'w') as writer:
                        data = reader.read()
                        writer.write(data)
                    
                else:            
                    # if PGP key, convert to binary, ???, convert back
                    with open(dest, "w") as file:
                        file.write(key)
                
                # update mirror with new path
                mirror["key"] = dest
