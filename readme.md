# Spack Stack Builder

A tool for building a scientific software stack from a receipe for vClusters on CSCS' Alps infrastructure.

## Bootstrapping
Use the `bootstrap.sh` script to install the necessary dependencies. 
The dependencies are going to be installed under the `external` directory on the root directory of the project.

## Basic usage

The tool generates the make files and spack configurations that build the spack environments that are packaged together in the spack stack.
It can be thought of as equivalent to calling `cmake` or `configure`, before running make to run the configured build.

```bash
# configure the build
./bin/sstool -b$BUILD_PATH -r$RECIPE_PATH

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
* `packages.yaml`: the packages and software to be installed..
* `modules.yaml`: an _optional_ set of module generation rules.

### config

```yaml
name: nvgpu-basic
store: /user-environment
system: hohgant
spack:
    repo: https://github.com/spack/spack.git
    commit: 6408b51
```

* `name`: a plain text name for the environment
* `store`: the location where the environment will be mounted.
* `system`: the name of the vCluster on which the stack will be deployed.
    * one of `balfrin` or `hohgant`.
    * cluster-specific details such as the version and location of libfabric are used when configuring and building the stack.
* `spack`: which spack repository to use for installation.

### compilers

Take an  example configuration:
```yaml
compilers:
  bootstrap:
    specs:
    - gcc@11
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
    * `gcc:specs`: A list of _at least one_ specs of the form `gcc@version`.
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

### packages

The packages are configured as disjoint environments, each built with the same compiler, and configured with a single implementation of MPI.

#### example: a cpu-only gnu toolchain with MPI

```
# packages.yaml
packages:
    gcc-host:
      compiler:
          toolchain: gcc
          spec: gcc@11.3
      unify: true
      specs:
      - hdf5 +mpi
      - fftw +mpi
      mpi:
        spec: cray-mpich-binary
        gpu: false
```

An environment labelled `gcc-host` is built using `gcc@11.3` from the `gcc` compiler toolchanin (**note** the compiler spec must mach a compiler from the toolchain that was installed via the `compilers.yaml` file).
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
> The `cray-mpich-binary` spec is added to the list of generated packages automatically.
> By setting `packages:mpi` all packages that use the virtual dependency `+mpi` will use the same `cray-mpich-binary` implementation.

#### example: a gnu toolchain with MPI and NVIDIA GPU support

```yaml
# packages.yaml
packages:
    gcc-nvgpu:
      compiler:
          toolchain: gcc
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

The `packages:gcc-nvgpu:gpu` to `cuda` will build the `cray-mpich-binary` with support for GPU-direct.

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

#### example: a gnu toolchain that provides some common tools

```yaml
# packages.yaml
packages:
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

