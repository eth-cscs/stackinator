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


def _supports_concretization_cache(spack_version: str) -> bool:
    """Whether the given "major.minor" spack version supports the concretizer cache.

    The concretizer:concretization_cache config key was introduced in spack 1.1;
    spack 1.0 rejects it (its concretizer schema forbids unknown keys).
    """

    major_minor = tuple(int(x) for x in spack_version.split("."))
    return major_minor >= (1, 1)


class MirrorError(RuntimeError):
    """Exception class for errors thrown by mirror configuration problems."""


class Mirrors:
    """Fully validated and resolved definition of the spack mirrors for a recipe.

    The kinds of mirror have separate types:

      * buildcache     - at most one, fetches and stores built packages (so it alone
                         has the mount_specific flag). With a private key it signs
                         and pushes packages too; without one it is read-only. None
                         if no build cache is configured.
      * bootstrap      - at most one, used to bootstrap spack itself (a local spack
                         bootstrap mirror directory, or a remote url). Needs no key
                         (bootstrap binaries are sha256-verified) and is emitted to
                         bootstrap.yaml, not the mirrors list. None if absent.
      * source_mirrors - a name -> config mapping of any number of read-only source
                         mirrors (spack mirrors.yaml entries). They need no key:
                         sources are verified against the checksums in the package
                         recipes, never with gpg.
      * source_cache   - at most one, a writable local directory that spack fills as
                         it fetches sources (spack config:source_cache). None if
                         absent. This is not a mirror: it has no key and no url, and
                         is emitted to config.yaml rather than mirrors.yaml.
      * concretizer_cache - at most one, a writable local directory persisting spack's
                         concretization results (concretizer:concretization_cache).
                         None if absent. Like source_cache it is not a mirror; it is
                         emitted to concretizer.yaml. It is only emitted for spack
                         >= 1.1 (spack 1.0 rejects the config key); when requested
                         against spack 1.0 it is skipped with a warning.

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
    BOOTSTRAP_YAML = "bootstrap.yaml"
    CONCRETIZER_YAML = "concretizer.yaml"

    def __init__(
        self,
        system_config_root: pathlib.Path,
        mount_path: pathlib.Path,
        spack_version: str,
        mirror_file: Optional[pathlib.Path] = None,
        cmdline_cache: Optional[pathlib.Path] = None,
    ):
        """Load and fully resolve the mirror configuration.

        Mirrors are supplied with the --mirror command line option (mirror_file).
        mount_path is the recipe mount point (used to make a build cache mount-specific).
        spack_version is the best-effort "major.minor" spack version, used to gate the
        concretizer cache (only emitted for spack >= 1.1).
        cmdline_cache is an optional legacy cache.yaml passed on the command line (--cache).

        Relative paths in the mirror file (e.g. gpg keys) are resolved relative to the
        directory containing the mirror file.
        """

        self._logger = root_logger
        self._mount_path = mount_path
        self._mirror_dir = mirror_file.parent if mirror_file is not None else None

        self.buildcache: Optional[Dict] = None
        self.bootstrap: Optional[Dict] = None
        self.source_mirrors: Dict[str, Dict] = {}
        self.source_cache: Optional[Dict] = None
        self.concretizer_cache: Optional[Dict] = None

        # The mirror configuration is supplied with --mirror, not the system
        # configuration. Reject a mirrors.yaml in the system config so it is not
        # silently ignored.
        if (system_config_root / "mirrors.yaml").exists():
            raise MirrorError(
                "A 'mirrors.yaml' in the system configuration is not supported.\n"
                "Provide the mirror configuration with the '--mirror' command line option."
            )

        # Load and schema-validate the mirror file given on the command line. If none
        # was given there are no mirrors; an empty config still validates (and picks up
        # schema defaults such as an empty sourcemirror map).
        if mirror_file is not None:
            if not mirror_file.is_file():
                raise MirrorError(f"The mirror configuration file '{mirror_file}' does not exist.")
            try:
                with mirror_file.open() as fid:
                    raw_mirrors = yaml.load(fid, Loader=yaml.SafeLoader)
            except (OSError, PermissionError) as err:
                raise MirrorError(f"Could not open/read mirror file '{mirror_file}'.\n{err}")
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
                "source": False,
                "binary": True,
                "public_key": None,
                "private_key": raw_cache.get("key"),
                "mount_specific": True,
            }
            self._logger.warning(
                "Configuring the buildcache from the system cache.yaml file.\n"
                "Please switch to using either the '--cache' option or the 'mirrors.yaml' file instead.\n"
                "The equivalent 'mirrors.yaml' would look like: \n\n"
                "buildcache:\n"
                "  mount_specific: true\n"
                f"  private_key: {self.buildcache['private_key']}\n"
                f"  url: {self.buildcache['url']}\n\n"
                "see https://eth-cscs.github.io/stackinator/mirrors for more information"
            )

        # The bootstrap mirror, the read-only source mirrors, the writable source
        # cache, and the writable concretizer cache, if any are defined.
        self.bootstrap = raw_mirrors.get("bootstrap")
        self.source_mirrors = raw_mirrors.get("sourcemirror") or {}
        self.source_cache = raw_mirrors.get("sourcecache")
        self.concretizer_cache = raw_mirrors.get("concretizer")

        # The source and concretizer caches are single writable local directories
        # (spack config:source_cache / concretizer:concretization_cache), not mirrors:
        # validate that each is an absolute path. Expand env vars now, because the
        # build sandbox runs `env --ignore-environment` and so would not expand them
        # at build time.
        for cache_name, cache in (("source", self.source_cache), ("concretizer", self.concretizer_cache)):
            if cache is not None:
                path = os.path.expandvars(cache["path"])
                if not pathlib.Path(path).is_absolute():
                    raise MirrorError(f"The {cache_name} cache path '{path}' is not absolute")
                cache["path"] = path

        # The concretizer cache (concretizer:concretization_cache) was introduced in
        # spack 1.1; spack 1.0 rejects the config key. Determine whether to emit it
        # based on the best-effort spack version, and warn (not error) if it was
        # requested but cannot be configured.
        self._emit_concretizer_cache = self.concretizer_cache is not None and _supports_concretization_cache(
            spack_version
        )
        if self.concretizer_cache is not None and not self._emit_concretizer_cache:
            self._logger.warning(
                f"The concretizer cache is not supported by spack {spack_version} (requires >= 1.1) "
                "and will not be configured."
            )

        # Resolve the bootstrap mirror. It is either a remote url, or a local spack
        # bootstrap mirror directory (a `spack bootstrap mirror` output) whose own
        # metadata/{sources,binaries} directories we reference directly.
        self._bootstrap_remote = False
        self._bootstrap_root: Optional[str] = None
        self._bootstrap_metadata_dirs: List[str] = []
        if self.bootstrap is not None:
            url = self.bootstrap["url"]
            if self._is_remote_url(url):
                self._bootstrap_remote = True
            else:
                root = self._local_path(url)
                if not root.is_dir():
                    raise MirrorError(f"The bootstrap mirror directory '{root}' does not exist")
                present = [sub for sub in ("sources", "binaries") if (root / "metadata" / sub).is_dir()]
                if not present:
                    raise MirrorError(
                        f"The bootstrap mirror directory '{root}' has no 'metadata/sources' or "
                        f"'metadata/binaries' directory (is it a 'spack bootstrap mirror' output?)."
                    )
                self._bootstrap_root = root.as_posix()
                self._bootstrap_metadata_dirs = present

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

        # The build cache may provide a public key, used to verify the packages
        # fetched from it. It is the only mirror with keys at all: sources (and
        # bootstrap binaries) are checksum-verified, and spack consults the gpg
        # keyring only when verifying signed build-cache binaries.
        if self.buildcache is not None and self.buildcache["public_key"] is not None:
            name = self.buildcache["name"]
            self._key_files.append((key_store / f"{name}.pub.gpg", self._read_key(self.buildcache["public_key"], name)))

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

    @staticmethod
    def _is_remote_url(url: str) -> bool:
        """True if url is a remote url (has a non-file scheme and a host)."""

        parsed = urllib.parse.urlparse(url)
        return bool(parsed.scheme) and parsed.scheme != "file" and bool(parsed.netloc)

    @staticmethod
    def _local_path(url: str) -> pathlib.Path:
        """The local filesystem path for a file:// url or a bare path (env vars expanded)."""

        if url.startswith("file://"):
            url = url[len("file://") :]
        return pathlib.Path(os.path.expandvars(url))

    # the spack mirror connection fields (everything that may appear inside a
    # fetch/push block, or at the top level of a mirror entry as a shorthand).
    _CONNECTION_KEYS = ("url", "view", "profile", "endpoint_url", "access_token_variable", "access_pair")

    @classmethod
    def _connection(cls, entry: Dict, key: str, mount_path: Optional[pathlib.Path] = None) -> Optional[Dict]:
        """Resolve a mirror entry's fetch/push connection to a spack connection dict.

        The connection comes from the entry's explicit `key` (either a url string or a
        connection object), falling back to the entry's top-level connection fields
        (url + auth) when no explicit fetch/push block is given - matching how spack
        applies a top-level url/auth to a mirror with no fetch/push. Returns None if
        no url can be resolved. When mount_path is set the url gains the mount point as
        a sub-directory (mount-specific build caches).
        """

        conn = entry.get(key)
        if conn is None:
            # shorthand: assemble the connection from the entry's top-level fields
            conn = {k: entry[k] for k in cls._CONNECTION_KEYS if entry.get(k) is not None}
        elif isinstance(conn, str):
            conn = {"url": conn}
        else:
            # copy so the relocation below never mutates the stored config
            conn = dict(conn)

        if "url" not in conn:
            return None

        if mount_path is not None:
            conn["url"] = conn["url"].rstrip("/") + "/" + mount_path.as_posix().lstrip("/")
        return conn

    @staticmethod
    def _add_optional_flags(entry: Dict, mirror: Dict):
        """Pass the optional spack mirror flags (signed, autopush) through if set.

        These have no default in the schema, so they are present only when the user set
        them; they are copied verbatim into the emitted spack mirror entry.
        """

        for flag in ("signed", "autopush"):
            if flag in mirror:
                entry[flag] = mirror[flag]

    def _read_key(self, key: str, name: str) -> bytes:
        """Resolve a key (a file path or base64 blob) to validated gpg key bytes.

        A key is either a path - absolute, or relative to the mirror file's directory
        - or a base64-encoded blob inlined in the mirror file. The resulting bytes are
        checked to be genuine gpg key material before being accepted.
        """

        # if it is a path (absolute, or relative to the mirror file), read it
        path = pathlib.Path(os.path.expandvars(key))
        if not path.is_absolute():
            path = self._mirror_dir / path

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
            # a mount-specific build cache lives in a sub-directory named after the
            # mount point: spack binaries embed the install prefix, so each mount
            # point needs its own cache to avoid relocation issues.
            mount = self._mount_path if self.buildcache["mount_specific"] else None
            # spack requires both fetch and push connections to be present in the
            # mirror entry, even for a read-only (keyless) build cache. Whether
            # packages are actually pushed to the cache is governed separately by
            # push_to_build_cache (only a build cache with a signing key is pushed to).
            entry = {
                "source": self.buildcache["source"],
                "binary": self.buildcache["binary"],
                "fetch": self._connection(self.buildcache, "fetch", mount),
                "push": self._connection(self.buildcache, "push", mount),
            }
            self._add_optional_flags(entry, self.buildcache)
            spack_mirrors["mirrors"][self.buildcache["name"]] = entry

        for name, mirror in self.source_mirrors.items():
            entry = {
                "source": mirror["source"],
                "binary": mirror["binary"],
                "fetch": self._connection(mirror, "fetch"),
                "push": self._connection(mirror, "push"),
            }
            self._add_optional_flags(entry, mirror)
            spack_mirrors["mirrors"][name] = entry

        files[config_root / self.MIRRORS_YAML] = yaml.dump(
            spack_mirrors, default_flow_style=False, sort_keys=False
        ).encode()

        # the spack config.yaml setting the populate-as-you-go source cache (spack
        # config:source_cache).
        if self.source_cache is not None:
            config_yaml = {"config": {"source_cache": self.source_cache["path"]}}
            files[config_root / self.CONFIG_YAML] = yaml.dump(config_yaml, default_flow_style=False).encode()

        # the spack concretizer.yaml persisting concretization results. enable is set
        # explicitly because it is opt-in in spack 1.1 (on by default only in >= 1.2).
        # _emit_concretizer_cache gates this on the spack version (>= 1.1).
        if self._emit_concretizer_cache:
            concretizer_yaml = {
                "concretizer": {
                    "concretization_cache": {
                        "enable": True,
                        "url": self.concretizer_cache["path"],
                    }
                }
            }
            files[config_root / self.CONCRETIZER_YAML] = yaml.dump(concretizer_yaml, default_flow_style=False).encode()

        # the spack bootstrap.yaml, if a bootstrap mirror is set. Bootstrapping reads
        # bootstrap:sources (not the mirrors list), and each source's `metadata` is a
        # directory describing it. No gpg key is involved (bootstrap binaries are
        # sha256-verified).
        if self.bootstrap is not None:
            sources = []
            trusted = {}
            if self._bootstrap_remote:
                # a remote mirror: generate a local source descriptor pointing at it.
                # this covers source bootstrapping; remote binary bootstrapping (which
                # needs per-package sha256 metadata) is not supported.
                metadata_dir = config_root / "bootstrap" / "bootstrap-mirror"
                metadata_yaml = {"type": "install", "info": {"url": self.bootstrap["url"]}}
                files[metadata_dir / "metadata.yaml"] = yaml.dump(metadata_yaml, default_flow_style=False).encode()
                sources.append({"name": "bootstrap-mirror", "metadata": str(metadata_dir)})
                trusted["bootstrap-mirror"] = True
            else:
                # a local spack bootstrap mirror: reference its own metadata directories.
                for sub in self._bootstrap_metadata_dirs:
                    name = f"bootstrap-{sub}"
                    sources.append({"name": name, "metadata": f"{self._bootstrap_root}/metadata/{sub}"})
                    trusted[name] = True

            bootstrap_yaml = {"bootstrap": {"sources": sources, "trusted": trusted}}
            files[config_root / self.BOOTSTRAP_YAML] = yaml.dump(bootstrap_yaml, default_flow_style=False).encode()

        return files
