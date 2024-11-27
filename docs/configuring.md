# Configuring Spack Stacks

Stackinator generates the make files and spack configurations that build the spack environments that are packaged together in the spack stack.
It can be thought of as equivalent to calling `cmake` or `configure`, performed using the `stack-config` CLI tool:

```bash
# configure the build
./bin/stack-config --build $BUILD_PATH --recipe $RECIPE_PATH --system $SYSTEM_CONFIG_PATH
```

The following flags are required:

* `-b/--build`: the path where the [build](building.md) is to be performed.
* `-r/--recipe`: the path with the [recipe](recipes.md) yaml files that describe the environment.
* `-s/--system`: the path containing the [system configuration](cluster-config.md) for the target cluster.

The following flags are optional:

* `-c/--cache`: configure the [build cache](build-caches.md).
* `--develop`: introduce compatibility with Spack's `develop` branch (see below).
* `--spack_version`: explicitly set the Spack version used for template configuration (see below).
* `-m/--mount`: override the [mount point](installing.md) where the stack will be installed.
* `--version`: print the stackinator version.
* `-h/--help`: print help message.

## Support for different versions of Spack

Stackinator supports the latest two or three minor versions of Spack, while trying to keep track of the latest changes in the `develop` branch of Spack, which will be included in the next release.

!!! note
    Currently v0.21, v0.22 and v0.23 of Spack are supported.

    The next official version will be v1.0 -- for which Stackinator will most likely drop support for all of the v0.2x versions.

By default, Stackinator will inspect the name of the `spack:commit` field in the `config.yaml` recipe file, to determine the Spack version (e.g. `releases/v0.23` would set `spack_version="0.23"`).
This default can be overriden the:

* `--develop` flag, which sets `spack_version` to the version of the next release.
* the `--spack_version` option, through which the version can be set explicitly.

Explicitly setting the Spack version using either `--develop` or `--spack_version` is recommended when using a commit or branch of Spack from which it is not possible for `stack-config` to infer the correct version.


```bash
# configure the build
# the recipe's config.yaml uses a Spack commit later than the latest release
stack-config --build $BUILD_PATH --recipe $RECIPE_PATH --system $SYSTEM_CONFIG_PATH --develop

# configure the templates for compatibility with Spack v0.23
stack-config --build $BUILD_PATH --recipe $RECIPE_PATH --system $SYSTEM_CONFIG_PATH --spack_version=0.23

# v0.24 is the next version of Spack, so this is equivalent to using the --develop flag
stack-config --build $BUILD_PATH --recipe $RECIPE_PATH --system $SYSTEM_CONFIG_PATH --spack_version=0.24
```

!!! note
    Spack's `develop` is supported on a best-effort basis and the Stackinator might be broken from upstream changes in Spack before we notice them. If you notice that Spack's `develop` breaks the Stackinator tool, please open an issue and we will introduce the required workaround for `--develop`.

