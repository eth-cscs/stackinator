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
        "fake-mirror": {
            'url': 'https://github.com', 
            'enabled': True, 
            'bootstrap': False, 
            'cache': False, 
            'public_key': '../../test-gpg-pub.asc',
            'mount_specific': False},
        "buildcache-mirror": {
            'url': 'https://mirror.spack.io', 
            'enabled': True, 
            'bootstrap': False, 
            'cache': True, 
            'private_key': '../test-gpg-priv.asc',
            'mount_specific': False},
        "bootstrap-mirror": {
            'url': 'https://mirror.spack.io', 
            'enabled': True, 
            'bootstrap': True,
            'cache': False,
            'mount_specific': False}
    }

    with (systems_path/'../test-gpg-pub.asc').open('rb') as pub_key_file:
        key = base64.b64encode(pub_key_file.read()).decode()
        valid_mirrors['buildcache-mirror']['public_key'] = key

    assert mirrors_obj.mirrors == valid_mirrors
    assert mirrors_obj.bootstrap_mirrors == [name for name in valid_mirrors.keys() if valid_mirrors[name].get('bootstrap')]
    assert mirrors_obj.build_cache_mirror == [name for name in valid_mirrors.keys() if valid_mirrors[name].get('cache')].pop(0)
    
    for mir in mirrors_obj.mirrors:
        assert mirrors_obj.mirrors[mir].get('enabled')

def test_mirror_init_bad_url(systems_path):
    """Check that MirrorError is raised for a bad url."""

    path = systems_path / "mirror-bad-url"

    with pytest.raises(mirror.MirrorError):
        mirror.Mirrors(path)

def test_setup_configs(tmp_path, systems_path):
    """Test general config setup."""

    mir = mirror.Mirrors(systems_path/'mirror-ok')
    mir.setup_configs(tmp_path)

    assert (tmp_path/'mirrors.yaml').is_file()
    assert (tmp_path/'bootstrap').is_dir()
    assert (tmp_path/'key_store').is_dir()

def test_command_line_cache(systems_path):
    """Check that adding a cache from the command line works."""

    mirrors = mirror.Mirrors(systems_path/'mirror-ok', 
                             cmdline_cache=systems_path/'mirror-ok/cache.yaml')

    assert len(mirrors.mirrors) == 4
    # This should always be the build cache even though one is already defined.
    assert mirrors.build_cache_mirror == 'cmdline_cache'
    cache_mirror = mirrors.mirrors['cmdline_cache']
    assert cache_mirror['url'] == '/tmp/foo'
    assert cache_mirror['enabled']
    assert cache_mirror['cache']
    assert not cache_mirror['bootstrap']
    assert cache_mirror['mount_specific'] 

def test_create_spack_mirrors_yaml(tmp_path, systems_path):
    """Check that the mirrors.yaml passed to spack is correct"""

    valid_spack_yaml = {
        "mirrors": {
            "fake-mirror": {
                "fetch": {"url": "https://github.com"},
                "push": {"url": "https://github.com"},
            },
            "buildcache-mirror": {
                "fetch": {"url": "https://mirror.spack.io"},
                "push": {"url": "https://mirror.spack.io"},
            },
            "bootstrap-mirror": {
                "fetch": {"url": "https://mirror.spack.io"},
                "push": {"url": "https://mirror.spack.io"},
            }
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
        "sources": [
            {
                "name": "bootstrap-mirror",
                "metadata": str(tmp_path / "bootstrap/bootstrap-mirror"),
            }
        ],
        "trusted": {
            "bootstrap-mirror": True
        },
    }
    valid_metadata = {
        "type": "install",
        "info": "https://mirror.spack.io",
    }

    mirrors_obj = mirror.Mirrors(systems_path/'mirror-ok')
    mirrors_obj._create_bootstrap_configs(tmp_path)

    with (tmp_path/'bootstrap.yaml').open() as f:
        bs_data = yaml.safe_load(f)
    print(bs_data)
    print(valid_yaml)
    assert bs_data == valid_yaml

    with (tmp_path/'bootstrap/bootstrap-mirror/metadata.yaml').open() as f:
        metadata = yaml.safe_load(f)
    assert metadata == valid_metadata

def test_key_setup(systems_path, tmp_path):
    """Check that public keys are set up properly."""

    mirrors = mirror.Mirrors(systems_path/'mirror-ok')

    mirrors._key_setup(tmp_path)

    key_files = list(tmp_path.iterdir())
    assert {key_file.name for key_file in key_files} == {'buildcache-mirror.gpg', 'fake-mirror.gpg'}
    # The two files should be identical in content
    key_file_data = []
    for key_file in key_files:
        with key_file.open('rb') as file:
            key_file_data.append(file.read())
    assert key_file_data[0] == key_file_data[1]

@pytest.mark.parametrize("system_name", [
    'mirror-bad-key',
    'mirror-bad-keypath',
])
def test_key_setup_bad_key(tmp_path, systems_path, system_name):
    """asdfasdf"""

    mirrors = mirror.Mirrors(systems_path/system_name)
    with pytest.raises(mirror.MirrorError):
        mirrors._key_setup(tmp_path)



