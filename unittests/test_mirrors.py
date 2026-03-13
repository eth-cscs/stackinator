import pytest
import pathlib
import stackinator.mirror as mirror
import yaml

@pytest.fixture
def test_path():
    return pathlib.Path(__file__).parent.resolve()

@pytest.fixture
def systems_path(test_path):
    return test_path / "data" / "systems"

@pytest.fixture
def valid_mirrors(systems_path):
    mirrors = {}
    mirrors["fake-mirror"] = {'url': 'https://google.com', 'enabled': True, 'bootstrap': False, 'cache': False, 'mount_specific': False}
    mirrors["buildcache-mirror"] = {'url': 'https://cache.spack.io/', 'enabled': True, 'bootstrap': False, 'cache': True, 'mount_specific': False}
    mirrors["bootstrap-mirror"] = {'url': 'https://mirror.spack.io', 'enabled': True, 'bootstrap': True, 'cache': False, 'mount_specific': False}
    return mirrors

def test_mirror_init(systems_path, valid_mirrors):
    path = systems_path / "mirror-ok"
    print(path)
    mirrors_obj = mirror.Mirrors(path)
    print(mirrors_obj.mirrors.items())
    assert mirrors_obj.mirrors == valid_mirrors
    assert mirrors_obj.mirrors.bootstrap_mirrors == [mirror for mirror in valid_mirrors.values() if mirror.get('bootstrap')]
    assert mirrors_obj.mirrors.build_cache_mirror == [mirror for mirror in valid_mirrors.values() if mirror.get('buildcache')]
    # assert disabled mirror not in mirrors
    for mir in mirrors_obj.mirrors:
        assert mir["enabled"]
    # test that cmdline_cache gets added to mirrors?

def test_command_line_cache(systems_path):
    """Check that adding a cache from the command line works."""

    mirrors = mirror.Mirrors(systems_path/'mirror-ok', cmdline_cache=systems_path.as_posix())

    assert len(mirrors.mirrors) == 4
    

def test_create_spack_mirrors_yaml(systems_path):
    pass

def test_create_bootstrap_configs():
    pass

def test_key_setup():
    pass
