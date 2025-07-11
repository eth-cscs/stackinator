# Stackinator

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

!!! warning
    The `main` branch of Stackinator includes features for Spack v1.0, and may break older recipes.

    For existing recipes use Spack v0.23 and earlier, use [version 5](#versions):

    ```bash
    git clone --branch=releases/v5 https://github.com/eth-cscs/stackinator.git
    ```

The `bootstrap.sh` script will install the necessary dependencies, so that Stackinator can be run as a standalone application.

Once installed, add the `bin` sub-directory to your path:

```bash
export PATH="<stackinator-install-path>/bin:$PATH"
```

### Using Pip

Stackinator is available on PyPi:

```
pip install stackinator
```

!!! warning
    The PyPi package is only updated for releases, so you will likely be missing the latest and greatest features.
    Let us know if you need more regular PyPi updates.

### Versions

Stackinator version 6 will be the first release of Stackinator to support Spack 1.0, when it is released in June 2025.
There will be significant changes introduced in Spack 1.0, which will require making some non-trivial changes to Stackinator, and possibly adding breaking changes to the Stackinator recipe specification.

The git branch `releases/v5` will be maintained to provide support for all versions 0.21, 0.22 and 0.23 of Spack and existing recipes.

The `main` branch of Stackinator will contain 

!!! warning
    After the release of version 5, the main development branch was changed from `master` to `main`.

## Quick Start

Stackinator generates the make files and spack configurations that build the spack environments that are packaged together in the spack stack.
It can be thought of as equivalent to calling `cmake` or `configure`, before running make to run the configured build.

```bash
# configure the build
stack-config --build $BUILD_PATH --recipe $RECIPE_PATH --system $SYSTEM_CONFIG_PATH
```

Where the `BUILD_PATH` is the path where the build will be configured, the `RECIPE_PATH` contains the [recipe](recipes.md) for the sotware stack, and `SYSTEM_CONFIG_PATH` is the [system configuration](cluster-config.md) for the cluster being targeted.

Once configured, the build stack is built in the build path using make:

```bash
# build the spack stack
cd $BUILD_PATH
env --ignore-environment PATH=/usr/bin:/bin:`pwd`/spack/bin make modules store.squashfs -j64
```

See the documentation on [building Spack stacks](building.md) for more information.

Once the build has finished successfully the software can be [installed](installing.md).

!!! alps
    On Alps the software stack can be tested using the [uenv](https://docs.cscs.ch/software/uenv/) image generated by the build:
    ```bash
    uenv start ./store.squashfs
    ```
