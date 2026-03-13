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
    mirrors["fake-mirror"] = {'url': 'https://google.com'}
    mirrors["buildcache-mirror"] = {'url': 'https://cache.spack.io/', 'buildcache': True}
    mirrors["bootstrap-mirror"] = {'url': 'https://mirror.spack.io', 'bootstrap': True}
    return mirrors

def test_mirror_init(systems_path, valid_mirrors):
    path = systems_path / "mirror_ok"
    mirrors = mirror.Mirrors(path)
    print(valid_mirrors)
    print(mirrors)
    assert mirrors == valid_mirrors
    assert mirrors.bootstrap_mirrors == [mirror for mirror in valid_mirrors if mirror["bootstrap"]]
    assert mirrors.build_cache_mirror == [mirror for mirror in valid_mirrors if mirror['buildcache']]
    # assert disabled mirror not in mirrors
    for mir in mirrors:
        assert mir["enabled"]
    # test that cmdline_cache gets added to mirrors?

def test_create_spack_mirrors_yaml(systems_path):
    pass

def test_create_bootstrap_configs():
    pass

def test_key_setup():
    pass