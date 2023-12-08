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
* `--develop`: introduce compatibility with Spack's `develop` branch.
* `-m/--mount`: override the [mount point](installing.md) where the stack will be installed.
* `--version`: print the stackinator version.
* `-h/--help`: print help message.

## Using Spack's `develop` branch
 
Stackinator supports the latest two minor versions of Spack. Since Spack has no stable major release yet, it has a short gap between deprecation and removal.

!!! note
    Currently v0.20 and v0.21 of Spack are supported, with best effort support of the latest developments in the `develop` branch of Spack (see below).

In order to use Spack's `develop` branch it is possible to configure the Spack stacks using the `--develop`.

```bash
# configure the build
# the recipe's config.yaml uses a Spack commit later than the latest release
./bin/stack-config --build $BUILD_PATH --recipe $RECIPE_PATH --system $SYSTEM_CONFIG_PATH --develop
```

!!! note
    Spack's `develop` is supported on a best-effort basis and the Stackinator might be broken from upstream changes in Spack before we notice them. If you notice that Spack's `develop` breaks the Stackinator tool, please open an issue and we will introduce the required workaround for `--develop`.

### Current Support

The `--develop` option currently handles the following the following:
 
* `spack env --with-view <name>` requires an argument.
    * v0.20 and earlier did not accept a named argument to `spack env --with-view`, instead requiring the presence of a view named `default`.
    * v0.21 requires the name of the view be passed as a positional argument.
    * if `--develop` is passed, or `v0.21` is detected.
    * will be removed when v0.21 is the oldest supported version of Spack.

Once the supported Spack releases are updated, the changes introduced by `--develop` will be used by default.
