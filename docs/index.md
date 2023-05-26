# Stackinator

hello world.

A tool for building a scientific software stack from a recipe on HPE Cray EX systems.

It is used to build software vClusters on Alps infrastructure at CSCS.

## Getting Stackinator

### From GitHub (recommended)

To get the latest version, download directly from GitHub.

``` bash
git clone https://github.com/eth-cscs/stackinator.git
cd stackinator
./bootstrap.sh
```

The `bootstraph.sh` script will install the necessary dependencies, so that stackinator can be run as a standalone application.

Once installed, add the `bin` sub-directory it to your path:

```bash
export PATH="<stackinator-install-path>/bin:$PATH"
```

### Using Pip

Stackinator is available on pip:

```
pip install stackinator
```

!!! warning
    The PyPi package is only updated for releases, so you will likely be missing the latest and greatest features. Let us know if you need more regular PyPi updates.

## Quick Start

Stackinator generates the make files and spack configurations that build the spack environments that are packaged together in the spack stack.
It can be thought of as equivalent to calling `cmake` or `configure`, before running make to run the configured build.


```bash
# configure the build
stack-config --build $BUILD_PATH --recipe $RECIPE_PATH --system $SYSTEM_CONFIG_PATH
```

TODO: Describe the above

Then we can build the stack

```bash
# build the spack stack
cd $BUILD_PATH
env --ignore-environment PATH=/usr/bin:/bin:`pwd`/spack/bin make modules store.squashfs -j64
```

TODO: Describe the above

Then mount the stack:
```bash
squashfs-mount store.squashfs /user-environment bash
ls /user-environment
```

TODO: Describe the above

``` py
import arbor

print(arbor.version)
for i in range(42):
  x = 2*i
```

hello world.


## Configuring a stack

Stackinator generates the make files and spack configurations that build the spack environments that are packaged together in the spack stack.
It can be thought of as equivalent to calling `cmake` or `configure`, before running make to run the configured build.

```bash
# configure the build
./bin/stack-config --build $BUILD_PATH --recipe $RECIPE_PATH --system $SYSTEM_CONFIG_PATH

# build the spack stack
cd $BUILD_PATH
env --ignore-environment PATH=/usr/bin:/bin:`pwd`/spack/bin make modules store.squashfs -j64
```

The flags are required:

* `-b/--build`: the path where the build is to be performed.
* `-r/--recipe`: the path with the recipe yaml files that describe the environment.
* `-s/--system`: the path containing the system configuration for the target cluster.

The following flags are optional

* `-c/--cache`: configure the build cache.
* `-m/--mount`: override the mount point of the environment.
* `--version`: print the stackinator version.
* `-h/--help`: print help message.
* `-d/--debug`: more verbose output.

## Building a stack
