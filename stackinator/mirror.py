
from typing import Optional, List, Dict
import base64
import io
import magic
import os
import pathlib
import urllib.error
import urllib.request
import yaml

from . import schema, root_logger

class MirrorError(RuntimeError):
    """Exception class for errors thrown by mirror configuration problems."""

class Mirrors:
    """Manage the definition of mirrors in a recipe."""

    KEY_STORE_DIR = 'key_store'
    MIRRORS_YAML = 'mirrors.yaml'

    def __init__(self, system_config_root: pathlib.Path, cmdline_cache: Optional[str] = None, 
                 mount_point: Optional[pathlib.Path] = None):
        """Configure mirrors from both the system 'mirror.yaml' file and the command line."""

        self._system_config_root = system_config_root
        self._mount_point = mount_point

        self._logger = root_logger

        self.mirrors = self._load_mirrors(cmdline_cache)
        self._check_mirrors()
 
        self.build_cache_mirror : Optional[str] = \
            ([name for name, mirror in self.mirrors.items() if mirror.get('cache', False)] 
             + [None]).pop(0)
        self.bootstrap_mirrors = [name for name, mirror in self.mirrors.items()
                                    if mirror.get('bootstrap', False)]

        # Will hold a list of all the gpg keys (public and private)
        self._keys: Optional[List[pathlib.Path]] = [] 

    def _load_mirrors(self, cmdline_cache: Optional[str]) -> Dict[str, Dict]:
        """Load the mirrors file, if one exists."""
        path = self._system_config_root/"mirrors.yaml"
        if path.exists():
            with path.open() as fid:
                # load the raw yaml input
                raw = yaml.load(fid, Loader=yaml.SafeLoader)

            # validate the yaml
            schema.MirrorsValidator.validate(raw)

            mirrors = {name: mirror for name, mirror in raw.items() if mirror["enabled"]}
        else:
            mirrors = {}

        # Add or set the cache given on the command line as the buildcache destination
        if cmdline_cache is not None:
            existing_mirror = [mirror for mirror in mirrors if mirror['name'] == cmdline_cache]
            # If the mirror name given on the command line isn't in the config, assume it 
            # is the URL to a build cache.
            if not existing_mirror:
                mirrors['cmdline_cache'] = {
                        'url': cmdline_cache,
                        'description': "Cache configured via command line.",
                        'enabled': True,
                        'cache': True,
                        'bootstrap': False,
                        'mount_specific': True,
                    }

        # Load the cache as defined by the deprecated 'cache.yaml' file.
        mirrors['legacy_cache_cfg'] = self._load_legacy_cache()

        caches = [mirror for mirror in mirrors.values() if mirror['cache']]
        if len(caches) > 1:
            raise MirrorError(
                "Mirror config has more than one mirror specified as the build cache destination.\n"
                "Some of these may have come from a legacy 'cache.yaml' or the '--cache' option.\n"
                f"{self._pp_yaml(caches)}")

        return mirrors

    @staticmethod 
    def _pp_yaml(object):
        """Pretty print the given object as yaml."""

        example_yaml_stream = io.StringIO()
        yaml.dump(object, example_yaml_stream, default_flow_style=False)
        return example_yaml_stream.getvalue()

    def _load_legacy_cache(self):
        """Load the mirror definition from the legacy cache.yaml file."""

        cache_config_path = self._system_config_root/'cache.yaml'

        if cache_config_path.is_file():
            
            with cache_config_path.open('r') as file: 
                try:
                    raw = yaml.load(file, Loader=yaml.SafeLoader)
                except ValueError as err:
                    raise MirrorError(
                        f"Error loading yaml from cache config at '{cache_config_path}'\n{err}")

            try:
                schema.CacheValidator.validate(raw)
            except ValueError as err:
                raise MirrorError(
                    f"Error validating contents of cache config at '{cache_config_path}'.\n{err}")

            mirror_cfg = {
                'url': f'file://{raw['root']}',
                'description': "Buildcache dest loaded from legacy cache.yaml",
                'buildcache_push': True,
                'mount_specific': True,
                'enabled': True,
                'private_key': raw['key'],
            }

            self._logger.warning("Configuring the buildcache from the system cache.yaml file.\n"
                "Please switch to using either the '--cache' option or the 'mirrors.yaml' file instead.\n"
                f"The equivalent 'mirrors.yaml' would look like: \n{self._pp_yaml([mirror_cfg])}")

            return mirror_cfg

    def _check_mirrors(self):
        """Validate the mirror config entries."""

        for name, mirror in self.mirrors.items():
            url = mirror["url"]
            if url.startswith("file://"):
                # verify that the root path exists
                path = pathlib.Path(os.path.expandvars(url))
                if not path.is_absolute():
                    raise MirrorError(f"The mirror path '{path}' for mirror '{name}' is not absolute")
                if not path.is_dir():
                    raise MirrorError(f"The mirror path '{path}' for mirror '{name}' is not a directory")

                mirror["url"] = path

            elif url.startswith("https://"):
                try:
                    request = urllib.request.Request(url, method='HEAD')
                    urllib.request.urlopen(request)
                except urllib.error.URLError as e:
                    raise MirrorError(
                        f"Could not reach the mirror url '{url}'. " 
                        f"Check the url listed in mirrors.yaml in system config. \n{e.reason}")

    @property
    def keys(self):
        """Return the list of public and private key file paths."""

        if self._keys is None:
            raise RuntimeError("The mirror.keys method was accessed before setup_configs() was called.")

        return self._keys


    def setup_configs(self, config_root: pathlib.Path):
        """Setup all mirror configs in the given config_root."""

        self._key_setup(config_root/self.KEY_STORE_DIR)
        self._create_spack_mirrors_yaml(config_root/self.MIRRORS_YAML)
        self._create_bootstrap_configs(config_root)

    def _create_spack_mirrors_yaml(self, dest: pathlib.Path):
        """Generate the mirrors.yaml for our build directory."""

        raw = {"mirrors": {}}

        for name, mirror in self.mirrors.items():
            name = mirror["name"]
            url = mirror["url"]

            raw["mirrors"][name] = {
                "fetch": {"url": url},
                "push": {"url": url},
            }

        with dest.open("w") as file:
            yaml.dump(raw, file, default_flow_style=False)

    def _create_bootstrap_configs(self, config_root: pathlib.Path):
        """Create the bootstrap.yaml and bootstrap metadata dirs in our build dir."""

        if not self.bootstrap_mirrors:
            return
        
        bootstrap_yaml = {
            'sources': [],
            'trusted': {},
        }

        for name in self.bootstrap_mirrors:
            bs_mirror_path = config_root/f'bootstrap/{name}'
            mirror = self.mirrors[name]
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

    def _key_setup(self, key_store: pathlib.Path):
        """Validate mirror keys, relocate to key_store, and update mirror config with new key paths."""
        
        self._keys = []
        key_store.mkdir(exist_ok=True)

        for name, mirror in self.mirrors.items():
            if mirror.get("public_key") is None:
                continue

            key = mirror["public_key"]

            # key will be saved under key_store/mirror_name.gpg

            dest = pathlib.Path(key_store / f"{name}.gpg")

            # if path, check if abs path, if not, append sys config path in front and check again
            path = pathlib.Path(os.path.expandvars(key))
            if not path.is_absolute():
                #try prepending system config path
                path = self._system_config_root/path

            if path.exists():
                if not path.is_file():
                    raise MirrorError(
                        f"The key path '{path}' is not a file. \n"
                        f"Check the key listed in mirrors.yaml in system config.")
                
                with open(path, 'rb') as reader:
                    binary_key = reader.read()
                
            # convert base64 key to binary
            else:
                try:
                    binary_key = base64.b64decode(key)
                except ValueError:
                    raise MirrorError(
                        f"Key for mirror '{name}' is not valid. \n"
                        f"Must be a path to a GPG public key or a base64 encoded GPG public key. \n"
                        f"Check the key listed in mirrors.yaml in system config.")
            
            file_type = magic.from_buffer(binary_key, mime=True)
            print("magic type:" , file_type)
            if file_type != "application/x-gnupg-keyring":
                raise MirrorError(
                    f"Key for mirror {name} is not a valid GPG key. \n"
                    f"Check the key listed in mirrors.yaml in system config.")

            # copy key to new destination in key store
            with open(dest, 'wb') as writer:
                writer.write(binary_key)

            self._keys.append(dest)
