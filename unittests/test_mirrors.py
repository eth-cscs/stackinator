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


def test_mirror_init(systems_path):
    """Check that Mirror objects are initialized correctly."""
    path = systems_path / "mirror-ok"
    mirrors_obj = mirror.Mirrors(path)

    valid_mirrors = {
        "bootstrap": {
            "url": "https://mirror.spack.io",
            "enabled": True,
        },
        "buildcache": {
            "url": "https://mirror.spack.io",
            "enabled": True,
            "private_key": "../../test-gpg-priv.asc",
            "mount_specific": False,
            "cmdline": False,
        },
        "mirror1": {
            "url": "https://github.com",
            "enabled": True,
        },
        "mirror2": {
            "url": "https://github.com/spack",
            "enabled": True,
        }
    }

    # with (systems_path / "../test-gpg-pub.asc").open("rb") as pub_key_file:
    #     key = base64.b64encode(pub_key_file.read()).decode()
    #     valid_mirrors["buildcache"]["public_key"] = key

    assert mirrors_obj.mirrors == valid_mirrors

    assert mirrors_obj.build_cache_mirror == "buildcache"

    for mir in mirrors_obj.mirrors:
        assert mirrors_obj.mirrors[mir].get("enabled")


def test_mirror_init_bad_url(systems_path):
    """Check that MirrorError is raised for a bad url."""

    path = systems_path / "mirror-bad-url"

    with pytest.raises(mirror.MirrorError):
        mirror.Mirrors(path)


def test_setup_configs(tmp_path, systems_path):
    """Test general config setup."""

    mir = mirror.Mirrors(systems_path / "mirror-ok")
    mir.setup_configs(tmp_path)

    assert (tmp_path / "mirrors.yaml").is_file()
    assert (tmp_path / "bootstrap").is_dir()
    assert (tmp_path / "key_store").is_dir()


def test_command_line_cache(systems_path):
    """Check that adding a cache from the command line works."""

    mirrors = mirror.Mirrors(systems_path / "mirror-ok", cmdline_cache=systems_path / "mirror-ok/cache.yaml")

    assert len(mirrors.mirrors) == 4
    # This should always be the build cache even though one is already defined.
    assert mirrors.build_cache_mirror == "cmdline_cache"
    cache_mirror = mirrors.mirrors["buildcache"]
    assert cache_mirror["url"] == "/tmp/foo"
    assert cache_mirror["enabled"]
    assert cache_mirror["cmdline"]
    assert cache_mirror["mount_specific"]


def test_create_spack_mirrors_yaml(tmp_path, systems_path):
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
                "fetch": {"url": "https://github.com"},
                "push": {"url": "https://github.com"},
            },
            "mirror2": {
                "fetch": {"url": "https://github.com/spack"},
                "push": {"url": "https://github.com/spack"},
            },
        }
    }

    dest = tmp_path / "test_output.yaml"
    mirrors_obj = mirror.Mirrors(systems_path / "mirror-ok")
    mirrors_obj._create_spack_mirrors_yaml(dest)

    with dest.open() as f:
        data = yaml.safe_load(f)

    assert data == valid_spack_yaml


def test_create_bootstrap_configs(tmp_path, systems_path):
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
        }
    }

    mirrors_obj = mirror.Mirrors(systems_path / "mirror-ok")
    mirrors_obj._create_bootstrap_configs(tmp_path)

    with (tmp_path / "bootstrap.yaml").open() as f:
        bs_data = yaml.safe_load(f)
    print(bs_data)
    print(valid_yaml)
    assert bs_data == valid_yaml

    with (tmp_path / "bootstrap/bootstrap-mirror/metadata.yaml").open() as f:
        metadata = yaml.safe_load(f)
    assert metadata == valid_metadata


def test_key_setup(systems_path, tmp_path):
    """Check that public keys are set up properly."""

    mirrors_key_file = mirror.Mirrors(systems_path / "mirror-ok")
    key_dir = tmp_path / "key_dir"
    mirrors_raw_key = mirror.Mirrors(systems_path / "mirror-ok-raw-key")
    raw_dir = tmp_path / "raw_dir"

    mirrors_key_file._key_setup(key_dir)
    mirrors_raw_key._key_setup(raw_dir)

    key_file, = (p for p in key_dir.iterdir() if p.is_file())
    assert key_file.name == "buildcache.pgp"

    raw_key_file, = (p for p in key_dir.iterdir() if p.is_file())
    assert raw_key_file.name == "buildcache.pgp"

    # The two files should be identical in content
    with key_file.open("rb") as file:
        key_file_data = file.read()
    with raw_key_file.open("rb") as file:
        raw_key_file_data = file.read()
    assert key_file_data == raw_key_file_data


@pytest.mark.parametrize(
    "system_name",
    [
        "mirror-bad-key",
        "mirror-bad-keypath",
    ],
)
def test_key_setup_bad_key(tmp_path, systems_path, system_name):
    """Check that MirrorError is raised for bad keys"""

    with pytest.raises(mirror.MirrorError):
        mirrors = mirror.Mirrors(systems_path / system_name)
