# Spack Stack Builder

A tool for building a scientific software stack from a recipe for vClusters on CSCS' Alps infrastructure.

## Bootstrapping
Use the `bootstrap.sh` script to install the necessary dependencies. 
The dependencies are going to be installed under the `external` directory on the root directory of the project.

## Basic usage

The tool generates the make files and spack configurations that build the spack environments that are packaged together in the spack stack.
It can be thought of as equivalent to calling `cmake` or `configure`, before running make to run the configured build.

```bash
# configure the build
./bin/stack-config -b$BUILD_PATH -r$RECIPE_PATH

# build the spack stack
cd $BUILD_PATH
env --ignore-environment PATH=/usr/bin:/bin:`pwd`/spack/bin make modules store.squashfs -j64

# mount the stack
squashfs-run store.squashfs bash
```
* `-b, --build`: the path where the build stage
* `-r, --recipe`: the path with the recipe yaml files that describe the environment.
* `-d, --debug`: print detailed python error messages.

## Recipes

A recipe is the input provided to the tool. A recipe is comprised of the following yaml files in a directory:

* `config.yaml`: common configuration for the stack.
* `compilers.yaml`: the compilers provided by the stack.
* `environments.yaml`: environments that contain all the software packages.
* `modules.yaml`: _optional_ module generation rules
    * follows the spec for (spack mirror configuration)[https://spack.readthedocs.io/en/latest/mirrors.html]
* `packages.yaml`: _optional_ package rules.
    * follows the spec for (spack package configuration)[https://spack.readthedocs.io/en/latest/build_settings.html]

### config

```yaml
name: nvgpu-basic
store: /user-environment
system: hohgant
spack:
    repo: https://github.com/spack/spack.git
    commit: 6408b51
modules: True
```

* `name`: a plain text name for the environment
* `store`: the location where the environment will be mounted.
* `system`: the name of the vCluster on which the stack will be deployed.
    * one of `balfrin` or `hohgant`.
    * cluster-specific details such as the version and location of libfabric are used when configuring and building the stack.
* `spack`: which spack repository to use for installation.
* `mirrors`: _optional_ configure use of build caches, see [build cache documentation](docs/build-cache.md).
* `modules`: _optional_ enable/diasble module file generation (default `True`).

### compilers

Take an  example configuration:
```yaml
bootstrap:
  spec: gcc@11
gcc:
  specs:
  - gcc@11
llvm:
  requires: gcc@11
  specs:
  - nvhpc@21.7
  - llvm@14
```

The compilers are built in multiple stages:

1. *bootstrap*: A bootstrap gcc compiler is built using the system compiler (currently gcc 4.7.5).
    * `gcc:specs`: single spec of the form `gcc@version`.
    * The selected version should have full support for the target architecture in order to build optimised gcc toolchains in step 2.
2. *gcc*: The bootstrap compiler is then used to build the gcc version(s) provided by the stack.
    * `gcc:specs`: A list of _at least one_ of the specs of the form `gcc@version`.
3. *llvm*: (optional) The nvhpc and/or llvm toolchains are build using one of the gcc toolchains installed in step 2.
    * `llvm:specs`: a list of specs of the form `nvhpc@version` or `llvm@version`.
    * `llvm:requires`: the version of gcc from step 2 that is used to build the llvm compilers.

The first two steps are required, so that the simplest stack will provide at least one version of gcc compiled for the target architecture.

> **Note**
>
> Don't provide full specs, because the tool will insert "opinionated" specs for the target node type, for example:
> * `nvhpc@21.7` generates `nvhpc@21.7 ~mpi~blas~lapack`
> * `llvm@14` generates `llvm@14 +clang targets=x86 ~gold ^ninja@kitware`
> * `gcc@11` generates `gcc@11 build_type=Release +profiled +strip`

### environments

The software packages are configured as disjoint environments, each built with the same compiler, and configured with a single implementation of MPI.

#### example: a cpu-only gnu toolchain with MPI

```
# environments.yaml
gcc-host:
  compiler:
      - toolchain: gcc
        spec: gcc@11.3
  unify: true
  specs:
  - hdf5 +mpi
  - fftw +mpi
  mpi:
    spec: cray-mpich-binary
    gpu: false
```

An environment labelled `gcc-host` is built using `gcc@11.3` from the `gcc` compiler toolchain (**note** the compiler spec must mach a compiler from the toolchain that was installed via the `compilers.yaml` file).
The tool will generate a `spack.yaml` specification:

```yaml
# spack.yaml
spack:
  include:
  - compilers.yaml
  - config.yaml
  view: false
  concretizer:
    unify: True
  specs:
  - fftw +mpi
  - hdf5 +mpi
  - cray-mpich-binary
  packages:
    all:
      compiler: [gcc@11.3]
    mpi:
      require: cray-mpich-binary
```

> **Note**
>
> The `cray-mpich-binary` spec is added to the list of package specs automatically.
> By setting `environments.ENV.mpi` all packages in the environment `ENV` that use the virtual dependency `+mpi` will use the same `cray-mpich-binary` implementation.

#### example: a gnu toolchain with MPI and NVIDIA GPU support

```yaml
# environments.yaml
gcc-nvgpu:
  compiler:
      - toolchain: gcc
        spec: gcc@11.3
  unify: true
  specs:
  - cuda@11.8
  - fftw +mpi
  - hdf5 +mpi
  mpi:
    spec: cray-mpich-binary
    gpu: cuda
```

The `environments:gcc-nvgpu:gpu` to `cuda` will build the `cray-mpich-binary` with support for GPU-direct.

```yaml
# spack.yaml
spack:
  include:
  - compilers.yaml
  - config.yaml
  view: false
  concretizer:
    unify: True
  specs:
  - cuda@11.8
  - fftw +mpi
  - hdf5 +mpi
  - cray-mpich-binary +cuda
  packages:
    all:
      compiler: [gcc@11.3]
    mpi:
      require: cray-mpich-binary
```

#### example: a nvhpc toolchain with MPI

To build a toolchain with NVIDIA HPC SDK, we provide two compiler toolchains:
- The `llvm:nvhpc` compiler;
- A version of gcc from the `gcc` toolchain, in order to build dependencies (like CMake) that can't be built with nvhpc. If a second compiler is not provided, Spack will fall back to the system gcc 4.7.5, and not generate zen2/zen3 optimized code as a result.

```yaml
# environments.yaml
prgenv-nvidia:
  compiler:
      - toolchain: llvm
        spec: nvhpc
      - toolchain: gcc
        spec: gcc@11.3
  unify: true
  specs:
  - cuda@11.8
  - fftw%nvhpc +mpi
  - hdf5%nvhpc +mpi
  mpi:
    spec: cray-mpich-binary
    gpu: cuda
```

The following `spack.yaml` is generated:

```yaml
# spack.yaml
spack:
  include:
  - compilers.yaml
  - config.yaml
  view: false
  concretizer:
    unify: True
  specs:
  - cuda@11.8
  - fftw%nvhpc +mpi
  - hdf5%nvhpc +mpi
  - cray-mpich-binary +cuda
  packages:
    all:
      compiler: [nvhpc, gcc@11.3]
    mpi:
      require: cray-mpich-binary
```

#### example: a gnu toolchain that provides some common tools

```yaml
# environments.yaml
tools:
  compiler:
      toolchain: gcc
      spec: gcc@11.3
  unify: true
  specs:
  - cmake
  - python@3.10
  - tmux
  - reframe
  mpi: false
  gpu: false
```

```yaml
# spack.yaml
spack:
  include:
  - compilers.yaml
  - config.yaml
  view: false
  concretizer:
    unify: True
  specs:
  - cmake
  - python@3.10
  - tmux
  - reframe
  packages:
    all:
      compiler: [gcc@11.3]
```

### modules

Modules are generated for the installed compilers and packages by spack. The default module generation rules set by the version of spack specified in `config.yaml` will be used if no `modules.yaml` file is provided.

To set rules for module generation, provide a `module.yaml` file as per the [spack documentation](https://spack.readthedocs.io/en/latest/module_file_support.html).

To disable module generation, set the field `config:modules:False` in `config.yaml`.

### packages

A spack `packages.yaml` file is provided by the tool for each target cluster. This file sets system dependencies, such as libfabric and slurm, which are expected to be provided by the cluster and not built by Spack. A recipe can provide an `packages.yaml` file, which is merged with the cluster-specific `packages.yaml`.

For example, to enforce every compiler and environment built use the versions of perl and git installed on the system, add a file like the following (with appropriate version numbers and prefixes, of course):

```yaml
# packages.yaml
packages:
  perl:
    buildable: false
    externals:
    - spec: perl@5.36.0
      prefix: /usr
  git:
    buildable: false
    externals:
    - spec: git@2.39.1
      prefix: /usr
```
