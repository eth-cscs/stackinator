# Configuring Spack Stacks

Stackinator generates the make files and spack configurations that build the spack environments that are packaged together in the spack stack.
It can be thought of as equivalent to calling `cmake` or `configure`, performed using the `stack-config` CLI tool:

```bash
# configure the build
stack-config --build $BUILD_PATH --recipe $RECIPE_PATH --system $SYSTEM_CONFIG_PATH
```

The following flags are required:

* `-b/--build`: the path where the [build](building.md) is to be performed.
* `-r/--recipe`: the path with the [recipe](recipes.md) yaml files that describe the environment.
* `-s/--system`: the path containing the [system configuration](cluster-config.md) for the target cluster.

The following flags are optional:

* `-c/--cache`: configure the [build cache](build-caches.md).
* `-m/--mount`: override the [mount point](installing.md) where the stack will be installed.
* `--version`: print the stackinator version.
* `-h/--help`: print help message.

## Support for different versions of Spack

Stackinator supports Spack version 1.0.

!!! note
    Currently v0.21, v0.22 and v0.23 of Spack are supported in the `releases/v5` branch of Stackinator.

!!! note
    Support for Spack 1.0 in the `main` branch is currently under development, and may be unstable.

