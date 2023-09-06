# Build Caches

Stackinator facilitates using Spack's binary build caches to speed up image builds.
Build caches are essential if you plan to build images regularly, as they generally lead to a roughly 10x speed up.
This is the difference between half an hour or 3 minutes to build a typical image.

## Using Build caches

To use a build cache, create a simple YAML file:

```yaml title='cache-config.yaml'
root: $SCRATCH/uenv-cache
key:  $SCRATCH/.keys/spack-push-key.gpg
```

To use the cache, pass the configuration as an option to `stack-config` via the `-c/--cache` flag:

```bash
stack-config -b $build_path -r $recipe_path -s $system_config -c cache-config.yaml
```

??? warning "If you using an old binary build cache"
    Since v3, Stackinator creates a sub-directory in the build cache for each mount point.
    For example, in the above example, the build cache for the `/user-environment` mount point would be `$SCRATCH/uenv-cache/user-environment`.
    The rationale for this is so that packages for different mount points are not mixed, to avoid having to relocate binaries.

    To continue using a build caches from before v3, first copy the `build_cache` path to a subdirectory, e.g.:

    ```bash
    mkdir $SCRATCH/uenv-cache/user-environment
    mv $SCRATCH/uenv-cache/build_cache $SCRATCH/uenv-cache/user-environment
    ```

### Build-only caches

A build cache can be configured to be read-only by not providing a `key` in the cache configuration file.

## Creating a Build Cache

To create a build cache we need two things:

1. An empty directory where the cache will be populated by Spack.
2. A private PGP key
    *  Only required for Stackinator to push packages to the cache when it builds a package that was not in the cache.

Creating the cache directory is easy! For example, to create a cache on your scratch storage:
```bash
mkdir $SCRATCH/uenv-cache
```

### Generating Keys

An installation of Spack can be used to generate the key file:

```bash
# create a key
spack gpg create <name> <e-mail>

# export key
spack gpg export --secret spack-push-key.gpg
```

See the [spack documentation](https://spack.readthedocs.io/en/latest/getting_started.html#gpg-signing) for more information about GPG keys.

### Managing Keys

The key needs to be in a location that is accessible during the build process, and secure.
To keep your PGP key secret, you can generate it then move it to a path with appropriate permissions.
In the example below, we create a path `.keys` for storing the key:
```bash
# create  .keys path is visible only to you
mkdir $SCRATCH/.keys
chmod 700 $SCRATCH/.keys

# generate the key
spack gpg create <name> <e-mail>
spack gpg export --secret $SCRATCH/.keys/spack-push-key.gpg
chmod 600 $SCRATCH/.keys/spack-push-key.gpg
```

The cache-configuration would look like the following, where we assume that the cache is in `$SCRATCH/uenv-cache`:
```yaml
root: $SCRATCH/uenv-cache
key: $SCRATCH/.keys/spack-push-key.gpg
```
!!! warning
    Don't blindly copy this documentation's advice on security settings.

!!! failure "Don't use `$HOME`"
    Don't put the keys in `$HOME`, because the build process remounts `~` as a tmpfs, and you will get error messages that Spack can't read the key.

## Force pushing to build cache

When build caches are enabled, all packages in a each Spack environment are pushed to the build cache after the whole environment has been built successfully -- nothing will be pushed to the cache if there is an error when building one of the packages.

When debugging a recipe, where failing builds have to be run multiple times, the overheads of rebuilding all packages from scratch can be wasteful.
To force push all packages that have been built, use the `cache-force` makefile target:

```bash
env --ignore-environment PATH=/usr/bin:/bin:`pwd`/spack/bin make cache-force
```
