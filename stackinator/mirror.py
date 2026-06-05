from typing import Dict, List, Optional, Tuple
import base64
import os
import pathlib
import urllib.parse
import yaml

import magic

from . import schema, root_logger


# GPG keys may be presented either ASCII-armored (these headers) or as binary
# data, in which case we fall back to libmagic to recognise the key.
ASCII_PGP_HEADERS = (
    b"-----BEGIN PGP PRIVATE KEY BLOCK-----",
    b"-----BEGIN PGP PUBLIC KEY BLOCK-----",
    b"-----BEGIN PGP MESSAGE-----",
    b"-----BEGIN PGP SIGNATURE-----",
)

# libmagic mime types that we accept as (binary) GPG key material.
GPG_KEY_MIME_TYPES = (
    "application/x-gnupg-keyring",
    "application/pgp-keys",
    "application/octet-stream",
)


class MirrorError(RuntimeError):
    """Exception class for errors thrown by mirror configuration problems."""


class Mirrors:
    """Fully validated and resolved definition of the spack mirrors for a recipe.

    The kinds of mirror have separate types:

      * buildcache     - at most one, fetches and stores built packages (so it alone
                         has the mount_specific flag). With a private key it signs
                         and pushes packages too; without one it is read-only. None
                         if no build cache is configured.
      * bootstrap      - at most one, used to bootstrap spack itself. None if absent.
      * source_mirrors - a name -> config mapping of any number of read-only source
                         mirrors (spack mirrors.yaml entries).
      * source_cache   - at most one, a writable local directory that spack fills as
                         it fetches sources (spack config:source_cache). None if
                         absent. This is not a mirror: it has no key and no url, and
                         is emitted to config.yaml rather than mirrors.yaml.

    All input processing - loading and schema-validating the system mirrors.yaml,
    validating urls, and reading/decoding/validating gpg keys - happens eagerly in
    the constructor, so any error is reported during recipe construction. Once
    constructed, the object holds nothing but resolved, validated data, which is
    presented to the builder as static artifacts via config_files() and
    gpg_key_paths().
    """

    KEY_STORE_DIR = "key_store"
    MIRRORS_YAML = "mirrors.yaml"
    CONFIG_YAML = "config.yaml"
    BOOTSTRAP_MIRROR = "bootstrap"

    def __init__(
        self,
        system_config_root: pathlib.Path,
        mount_path: pathlib.Path,
        cmdline_cache: Optional[pathlib.Path] = None,
    ):
        """Load and fully resolve the mirror configuration.

        Inputs are the system config's mirrors.yaml, the recipe mount path (used to
        make a build cache mount-specific), and an optional legacy cache.yaml passed
        on the command line (--cache).
        """

        self._logger = root_logger
        self._system_config_root = system_config_root
        self._mount_path = mount_path

        self.buildcache: Optional[Dict] = None
        self.bootstrap: Optional[Dict] = None
        self.source_mirrors: Dict[str, Dict] = {}
        self.source_cache: Optional[Dict] = None

        # Load and schema-validate the system mirrors.yaml (absent file is fine).
        mirrors_path = system_config_root / "mirrors.yaml"
        if mirrors_path.exists():
            try:
                with mirrors_path.open() as fid:
                    raw_mirrors = yaml.load(fid, Loader=yaml.SafeLoader)
            except (OSError, PermissionError) as err:
                raise MirrorError(f"Could not open/read mirrors.yaml file.\n{err}")
        else:
            raw_mirrors = {}

        try:
            schema.MirrorsValidator.validate(raw_mirrors)
        except ValueError as err:
            raise MirrorError(f"Mirror config does not comply with schema.\n{err}")

        # The build cache, if one is defined in mirrors.yaml. A build cache without
        # a private_key is read-only: spack fetches from it but never pushes to it.
        self.buildcache = raw_mirrors.get("buildcache")

        # A build cache passed via the deprecated cache.yaml file (the --cache CLI
        # option) takes precedence over a buildcache defined in mirrors.yaml.
        if cmdline_cache is not None:
            if not cmdline_cache.is_file():
                raise MirrorError(
                    f"Binary cache configuration path given on the command line '{cmdline_cache}' does not exist."
                )
            with cmdline_cache.open() as fid:
                try:
                    raw_cache = yaml.load(fid, Loader=yaml.SafeLoader)
                except ValueError as err:
                    raise MirrorError(f"Error loading yaml from cache config at '{cmdline_cache}'\n{err}")
            try:
                schema.CacheValidator.validate(raw_cache)
            except ValueError as err:
                raise MirrorError(f"Error validating contents of cache config at '{cmdline_cache}'.\n{err}")

            # a cache.yaml without a key configures a read-only (fetch-only) cache
            self.buildcache = {
                "name": "buildcache",
                "url": raw_cache["root"],
                "description": "Buildcache dest loaded from legacy cache.yaml",
                "public_key": None,
                "private_key": raw_cache.get("key"),
                "mount_specific": True,
                "cmdline": True,
            }
            self._logger.warning(
                "Configuring the buildcache from the system cache.yaml file.\n"
                "Please switch to using either the '--cache' option or the 'mirrors.yaml' file instead.\n"
                f"The equivalent 'mirrors.yaml' would look like: \n"
                f"{yaml.dump([self.buildcache], default_flow_style=False)}"
            )

        # The bootstrap mirror, the read-only source mirrors, and the writable
        # source cache, if any are defined.
        self.bootstrap = raw_mirrors.get("bootstrap")
        self.source_mirrors = dict(raw_mirrors["sourcemirror"])
        self.source_cache = raw_mirrors.get("sourcecache")

        # Validate that every mirror url is well-formed (see _validate_url).
        for name, mirror in self._iter_mirrors():
            self._validate_url(mirror["url"], name)

        # The source cache is a single writable local directory (spack
        # config:source_cache), not a mirror: validate that it is an absolute path.
        # Expand env vars now, because the build sandbox runs `env --ignore-environment`
        # and so would not expand them at build time.
        if self.source_cache is not None:
            path = os.path.expandvars(self.source_cache["path"])
            if not pathlib.Path(path).is_absolute():
                raise MirrorError(f"The source cache path '{path}' is not absolute")
            self.source_cache["path"] = path

        # Read, decode and validate every gpg key into memory. Each key is stored
        # as (path-relative-to-config-root, raw bytes); the builder writes these
        # verbatim into the build directory's key store.
        key_store = pathlib.PurePosixPath(self.KEY_STORE_DIR)
        self._key_files: List[Tuple[pathlib.PurePosixPath, bytes]] = []

        # A build cache that pushes packages signs them with its private key. A build
        # cache without a key is read-only, and is fetched from but never pushed to.
        if self.buildcache is not None and self.buildcache["private_key"] is not None:
            name = self.buildcache["name"]
            self._key_files.append(
                (key_store / f"{name}.priv.gpg", self._read_key(self.buildcache["private_key"], name))
            )

        # Any mirror may provide a public key, used to verify downloaded packages.
        for name, mirror in self._iter_mirrors():
            public_key = mirror["public_key"]
            if public_key is not None:
                self._key_files.append((key_store / f"{name}.pub.gpg", self._read_key(public_key, name)))

    @property
    def build_cache_mirror(self) -> Optional[str]:
        """The build cache mirror name, or None if no build cache is configured.

        A build cache is fetched from (and its keys trusted) whether or not it has a
        signing key; see push_to_build_cache for whether packages are pushed to it.
        """

        return self.buildcache["name"] if self.buildcache is not None else None

    @property
    def push_to_build_cache(self) -> Optional[str]:
        """The build cache mirror name to push built packages to, or None.

        Pushing requires a private signing key; a build cache configured without one
        is read-only - fetched from but never pushed to.
        """

        if self.buildcache is not None and self.buildcache["private_key"] is not None:
            return self.buildcache["name"]
        return None

    def _iter_mirrors(self):
        """Yield (spack mirror name, config dict) for every configured mirror.

        The build cache's name is configurable (the 'name' field); the bootstrap
        and source mirrors are named by their key in mirrors.yaml.
        """

        if self.buildcache is not None:
            yield self.buildcache["name"], self.buildcache
        if self.bootstrap is not None:
            yield self.BOOTSTRAP_MIRROR, self.bootstrap
        yield from self.source_mirrors.items()

    def _validate_url(self, url: str, name: str):
        """Validate that a mirror url is well-formed.

        Only the format of the url is checked: no attempt is made to connect to
        remote mirrors, because a valid-but-unreachable url would otherwise block
        until the network request times out.
        """

        if url.startswith("file://"):
            # local mirror: verify that the root path is an existing directory
            path = pathlib.Path(os.path.expandvars(url[len("file://") :]))
            if not path.is_absolute():
                raise MirrorError(f"The mirror path '{path}' for mirror '{name}' is not absolute")
            if not path.is_dir():
                raise MirrorError(f"The mirror path '{path}' for mirror '{name}' is not a directory")
            return

        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme:
            # a bare path is accepted if absolute (e.g. the legacy command line cache)
            if not pathlib.Path(url).is_absolute():
                raise MirrorError(f"The mirror url '{url}' for mirror '{name}' is not a valid url or absolute path")
        elif not parsed.netloc:
            # a remote mirror requires a well-formed url with both a scheme and a host
            raise MirrorError(f"The mirror url '{url}' for mirror '{name}' is not a valid url")

    def _read_key(self, key: str, name: str) -> bytes:
        """Resolve a key (a file path or base64 blob) to validated gpg key bytes.

        A key is either a path - absolute, or relative to the system config - or a
        base64-encoded blob inlined in mirrors.yaml. The resulting bytes are checked
        to be genuine gpg key material before being accepted.
        """

        # if it is a path (absolute, or relative to the system config), read it
        path = pathlib.Path(os.path.expandvars(key))
        if not path.is_absolute():
            path = self._system_config_root / path

        if path.is_file():
            binary_key = path.read_bytes()
        else:
            # otherwise it must be a base64-encoded key
            try:
                binary_key = base64.b64decode(key)
            except ValueError:
                raise MirrorError(
                    f"Key for mirror '{name}' is not valid: '{path}'. \n"
                    f"Must be a path to a GPG public key or a base64 encoded GPG public key. \n"
                    f"Check the key listed in mirrors.yaml in system config."
                )

        is_gpg_key = binary_key.startswith(ASCII_PGP_HEADERS) or (
            magic.from_buffer(binary_key, mime=True) in GPG_KEY_MIME_TYPES
        )
        if not is_gpg_key:
            raise MirrorError(
                f"Key for mirror {name} is not a valid GPG key. \n"
                f"The file (or base64) was readable, but the data itself was not a PGP key.\n"
                f"Check the key listed in mirrors.yaml in system config."
            )

        return binary_key

    def gpg_key_paths(self, config_root: pathlib.Path) -> List[pathlib.Path]:
        """The absolute paths the gpg keys are written to, for `spack gpg trust`."""

        return [config_root / relpath for relpath, _ in self._key_files]

    def config_files(self, config_root: pathlib.Path) -> Dict[pathlib.Path, bytes]:
        """The complete set of mirror config files to write under config_root.

        Returns a mapping of absolute file path -> file content.
        """

        files: Dict[pathlib.Path, bytes] = {}

        # the relocated gpg keys
        for relpath, content in self._key_files:
            files[config_root / relpath] = content

        # the spack mirrors.yaml
        spack_mirrors: Dict[str, Dict] = {"mirrors": {}}

        if self.buildcache is not None:
            url = self.buildcache["url"]
            # a mount-specific build cache lives in a sub-directory named after the
            # mount point: spack binaries embed the install prefix, so each mount
            # point needs its own cache to avoid relocation issues.
            if self.buildcache["mount_specific"]:
                url = url.rstrip("/") + "/" + self._mount_path.as_posix().lstrip("/")
            entry = {"fetch": {"url": url}}
            # only a build cache with a signing key is pushed to
            if self.buildcache["private_key"] is not None:
                entry["push"] = {"url": url}
            spack_mirrors["mirrors"][self.buildcache["name"]] = entry

        if self.bootstrap is not None:
            url = self.bootstrap["url"]
            spack_mirrors["mirrors"][self.BOOTSTRAP_MIRROR] = {"fetch": {"url": url}, "push": {"url": url}}

        # source mirrors are read-only and provide sources only: fetch url, no push.
        for name, mirror in self.source_mirrors.items():
            spack_mirrors["mirrors"][name] = {
                "source": True,
                "binary": False,
                "fetch": {"url": mirror["url"]},
            }

        files[config_root / self.MIRRORS_YAML] = yaml.dump(
            spack_mirrors, default_flow_style=False, sort_keys=False
        ).encode()

        # the spack config.yaml setting the writable, populate-as-you-go source cache
        if self.source_cache is not None:
            config_yaml = {"config": {"source_cache": self.source_cache["path"]}}
            files[config_root / self.CONFIG_YAML] = yaml.dump(config_yaml, default_flow_style=False).encode()

        # the bootstrap config and its mirror metadata, if a bootstrap mirror is set
        if self.bootstrap is not None:
            metadata_dir = config_root / "bootstrap" / "bootstrap-mirror"
            bootstrap_yaml = {
                "bootstrap": {
                    "sources": [{"name": "bootstrap-mirror", "metadata": str(metadata_dir)}],
                    "trusted": {"bootstrap-mirror": True},
                }
            }
            metadata_yaml = {"type": "install", "info": {"url": self.bootstrap["url"]}}

            files[metadata_dir / "metadata.yaml"] = yaml.dump(metadata_yaml, default_flow_style=False).encode()
            files[config_root / "bootstrap.yaml"] = yaml.dump(bootstrap_yaml, default_flow_style=False).encode()

        return files
