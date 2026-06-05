import base64
import pathlib
import pytest
import stackinator.mirror as mirror
import yaml


@pytest.fixture
def test_path():
    return pathlib.Path(__file__).parent.resolve()


@pytest.fixture
def systems_path(test_path):
    return test_path / "data" / "systems"


@pytest.fixture
def mount_path():
    return pathlib.Path("/user-environment")


def test_mirror_init(systems_path, mount_path):
    """Check that the three kinds of mirror are resolved into separate members."""
    mirrors_obj = mirror.Mirrors(systems_path / "mirror-ok", mount_path)

    with (systems_path / "../test-gpg-pub.asc").open("rb") as pub_key_file:
        pub_key_b64 = base64.b64encode(pub_key_file.read()).decode()

    # the build cache, with its schema-defaulted name and flags
    assert mirrors_obj.buildcache == {
        "name": "buildcache",
        "url": "https://mirror.spack.io",
        "private_key": "../../test-gpg-priv.asc",
        "public_key": pub_key_b64,
        "mount_specific": False,
        "cmdline": False,
    }

    assert mirrors_obj.bootstrap == {"url": "https://mirror.spack.io"}

    assert mirrors_obj.source_mirrors == {
        "mirror1": {"url": "https://github.com", "public_key": "../../test-gpg-pub.asc"},
        "mirror2": {"url": "https://github.com/spack"},
    }

    # the writable, populate-as-you-go source cache
    assert mirrors_obj.source_cache == {"path": "/scratch/spack-sources"}

    # the build cache mirror name is derived from the build cache's 'name' field
    assert mirrors_obj.build_cache_mirror == "buildcache"


def test_mirror_init_bad_url(systems_path, mount_path):
    """Check that MirrorError is raised for a bad url."""

    path = systems_path / "mirror-bad-url"

    with pytest.raises(mirror.MirrorError):
        mirror.Mirrors(path, mount_path)


def test_command_line_cache(systems_path, mount_path):
    """Check that adding a cache from the command line works."""

    mirrors = mirror.Mirrors(
        systems_path / "mirror-ok", mount_path, cmdline_cache=systems_path / "mirror-ok/cache.yaml"
    )

    # the command line cache overrides any build cache defined in mirrors.yaml,
    # and is named "buildcache" like any other build cache.
    assert mirrors.build_cache_mirror == "buildcache"
    assert mirrors.buildcache["name"] == "buildcache"
    assert mirrors.buildcache["url"] == "/tmp/foo"
    assert mirrors.buildcache["cmdline"]
    assert mirrors.buildcache["mount_specific"]

    # it has a signing key, so it is pushed to
    assert mirrors.push_to_build_cache == "buildcache"

    # the bootstrap and source mirrors from mirrors.yaml are still present
    assert mirrors.bootstrap is not None
    assert set(mirrors.source_mirrors) == {"mirror1", "mirror2"}


def test_keyless_command_line_cache(tmp_path, systems_path, mount_path):
    """A cache.yaml without a key configures a read-only (fetch-only) build cache."""

    mirrors = mirror.Mirrors(
        systems_path / "mirror-ok", mount_path, cmdline_cache=systems_path / "mirror-ok/cache-nokey.yaml"
    )

    # the cache exists (so it is fetched from), but has no signing key ...
    assert mirrors.build_cache_mirror == "buildcache"
    assert "private_key" not in mirrors.buildcache

    # ... so it is never pushed to
    assert mirrors.push_to_build_cache is None

    files = mirrors.config_files(tmp_path)

    # no private key is written
    assert tmp_path / "key_store" / "buildcache.priv.gpg" not in files

    # the mirror is emitted with a fetch url but no push url
    data = yaml.safe_load(files[tmp_path / "mirrors.yaml"])
    assert data["mirrors"]["buildcache"] == {"fetch": {"url": "/tmp/foo/user-environment"}}


def test_config_files(tmp_path, systems_path, mount_path):
    """Check that config_files presents the complete set of mirror config artifacts."""

    mirrors_obj = mirror.Mirrors(systems_path / "mirror-ok", mount_path)
    files = mirrors_obj.config_files(tmp_path)

    expected = {
        tmp_path / "mirrors.yaml",
        tmp_path / "config.yaml",
        tmp_path / "bootstrap.yaml",
        tmp_path / "bootstrap" / "bootstrap-mirror" / "metadata.yaml",
        tmp_path / "key_store" / "buildcache.priv.gpg",
        tmp_path / "key_store" / "buildcache.pub.gpg",
        tmp_path / "key_store" / "mirror1.pub.gpg",
    }
    assert set(files.keys()) == expected

    # every artifact is presented as raw bytes, ready to be written verbatim
    assert all(isinstance(content, bytes) for content in files.values())


def test_spack_mirrors_yaml(tmp_path, systems_path, mount_path):
    """Check that the mirrors.yaml passed to spack is correct"""

    valid_spack_yaml = {
        "mirrors": {
            "bootstrap": {
                "fetch": {"url": "https://mirror.spack.io"},
                "push": {"url": "https://mirror.spack.io"},
            },
            "buildcache": {
                "fetch": {"url": "https://mirror.spack.io"},
                "push": {"url": "https://mirror.spack.io"},
            },
            "mirror1": {
                "source": True,
                "binary": False,
                "fetch": {"url": "https://github.com"},
            },
            "mirror2": {
                "source": True,
                "binary": False,
                "fetch": {"url": "https://github.com/spack"},
            },
        }
    }

    mirrors_obj = mirror.Mirrors(systems_path / "mirror-ok", mount_path)
    files = mirrors_obj.config_files(tmp_path)
    data = yaml.safe_load(files[tmp_path / "mirrors.yaml"])

    assert data == valid_spack_yaml


def test_mount_specific_buildcache(tmp_path, systems_path, mount_path):
    """A mount_specific buildcache should have the mount point appended to its url.

    Spack binaries embed the install prefix (the mount point), so a mount_specific
    cache is namespaced per-mount-point to avoid relocation issues / collisions.
    """

    mirrors_obj = mirror.Mirrors(systems_path / "mirror-ok", mount_path)

    # mirror-ok's buildcache is mount_specific: false by default; enable it.
    mirrors_obj.buildcache["mount_specific"] = True

    files = mirrors_obj.config_files(tmp_path)
    data = yaml.safe_load(files[tmp_path / "mirrors.yaml"])

    # the buildcache url gains the mount point as a sub-directory ...
    assert data["mirrors"]["buildcache"]["fetch"]["url"] == "https://mirror.spack.io/user-environment"
    assert data["mirrors"]["buildcache"]["push"]["url"] == "https://mirror.spack.io/user-environment"

    # ... while other mirrors are left untouched.
    assert data["mirrors"]["mirror1"]["fetch"]["url"] == "https://github.com"


def test_mount_specific_disabled(tmp_path, systems_path, mount_path):
    """A buildcache with mount_specific false is unchanged, even when a mount point is set."""

    mirrors_obj = mirror.Mirrors(systems_path / "mirror-ok", mount_path)

    # confirm the fixture leaves the flag off
    assert mirrors_obj.buildcache["mount_specific"] is False

    files = mirrors_obj.config_files(tmp_path)
    data = yaml.safe_load(files[tmp_path / "mirrors.yaml"])

    assert data["mirrors"]["buildcache"]["fetch"]["url"] == "https://mirror.spack.io"


def test_bootstrap_configs(tmp_path, systems_path, mount_path):
    """Check that spack bootstrap configs are generated correctly"""

    valid_yaml = {
        "bootstrap": {
            "sources": [
                {
                    "name": "bootstrap-mirror",
                    "metadata": str(tmp_path / "bootstrap/bootstrap-mirror"),
                }
            ],
            "trusted": {"bootstrap-mirror": True},
        }
    }
    valid_metadata = {
        "type": "install",
        "info": {
            "url": "https://mirror.spack.io",
        },
    }

    mirrors_obj = mirror.Mirrors(systems_path / "mirror-ok", mount_path)
    files = mirrors_obj.config_files(tmp_path)

    bs_data = yaml.safe_load(files[tmp_path / "bootstrap.yaml"])
    assert bs_data == valid_yaml

    metadata = yaml.safe_load(files[tmp_path / "bootstrap/bootstrap-mirror/metadata.yaml"])
    assert metadata == valid_metadata


def test_keys(systems_path, tmp_path, mount_path):
    """Check that gpg keys are decoded, relocated and reported consistently."""

    mirrors_obj = mirror.Mirrors(systems_path / "mirror-ok", mount_path)
    files = mirrors_obj.config_files(tmp_path)

    # public keys are set up for the buildcache and mirror1
    pub_files = {p for p in files if p.name.endswith(".pub.gpg")}
    assert {p.name for p in pub_files} == {"buildcache.pub.gpg", "mirror1.pub.gpg"}

    # the buildcache public key (inline base64) and mirror1's (a file) are the same
    # key, so the decoded bytes must match
    assert files[tmp_path / "key_store/buildcache.pub.gpg"] == files[tmp_path / "key_store/mirror1.pub.gpg"]

    # gpg_key_paths reports exactly the key files that config_files writes
    key_files = {p for p in files if p.parent.name == "key_store"}
    assert set(mirrors_obj.gpg_key_paths(tmp_path)) == key_files


def test_source_cache_config(tmp_path, systems_path, mount_path):
    """The writable source cache is emitted to config.yaml as config:source_cache."""

    mirrors_obj = mirror.Mirrors(systems_path / "mirror-ok", mount_path)
    files = mirrors_obj.config_files(tmp_path)

    data = yaml.safe_load(files[tmp_path / "config.yaml"])
    assert data == {"config": {"source_cache": "/scratch/spack-sources"}}


def test_source_cache_absent(tmp_path, systems_path, mount_path):
    """No config.yaml is generated when no source cache is configured."""

    # mirror-no-sourcecache has no sourcecache entry
    mirrors_obj = mirror.Mirrors(systems_path / "mirror-no-sourcecache", mount_path)
    files = mirrors_obj.config_files(tmp_path)

    assert mirrors_obj.source_cache is None
    assert tmp_path / "config.yaml" not in files


@pytest.mark.parametrize(
    "system_name",
    [
        "mirror-bad-key",
        "mirror-bad-keypath",
        "mirror-bad-sourcecache",
    ],
)
def test_bad_config(systems_path, mount_path, system_name):
    """Check that MirrorError is raised at construction for bad keys or a bad source cache path."""

    with pytest.raises(mirror.MirrorError):
        mirror.Mirrors(systems_path / system_name, mount_path)
