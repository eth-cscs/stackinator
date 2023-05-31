# Recipes

A recipe is a description of all of the compilers and software packages to be installed, along with configuration of modules and environment scripts the stack will provide to users.
A recipe is comprised of the following yaml files in a directory:

* `config.yaml`: common configuration for the stack.
* `compilers.yaml`: the compilers provided by the stack.
* `environments.yaml`: environments that contain all the software packages.
* `modules.yaml`: _optional_ module generation rules
    * follows the spec for [spack module configuration](https://spack.readthedocs.io/en/latest/module_file_support.html)
* `packages.yaml`: _optional_ define external packages
    * follows the spec for [spack package configuration](https://spack.readthedocs.io/en/latest/build_settings.html)
* `repo`: _optional_ custom spack package definitions.

## Configuration

```yaml title="config.yaml"
name: prgenv-gnu
store: /user-environment
spack:
    repo: https://github.com/spack/spack.git
    commit: releases/v0.20
modules: true
```

* `name`: a plain text name for the environment
* `store`: the location where the environment will be mounted.
* `spack`: which spack repository to use for installation.
* `modules`: _optional_ enable/diasble module file generation (default `true`).

## Compilers

Take an  example configuration:
```yaml title="compilers.yaml"
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

!!! note
    Don't provide full specs, because the tool will insert "opinionated" specs for the target node type, for example:

    * `nvhpc@21.7` generates `nvhpc@21.7 ~mpi~blas~lapack`
    * `llvm@14` generates `llvm@14 +clang targets=x86 ~gold ^ninja@kitware`
    * `gcc@11` generates `gcc@11 build_type=Release +profiled +strip`

## Environments

The software packages to install using the compiler toolchains are configured as disjoint environments, each built with the same compiler, and configured with an optional implementation of MPI.
These are specified in the `environments.yaml` file.

```yaml title="environments.yaml high level overview"
env1:
  # the compiler toolchain(s) to use
  compiler:
      - toolchain: gcc
        spec: gcc@11.3
  # the optional MPI
  mpi:
    spec: cray-mpich
    gpu: true
  # whether to unify concretisation (true/false/when_possible)
  unify: true
  # list of software packages and their specs
  specs:
  - cuda11.8
  - hdf5 +mpi
  - fftw +mpi
  variants:
  - arch
```

### compilers

The `compiler` field describes a list compilers to use to build the software stack.
Each compiler toolchain is specified using toolchain and spec

```yaml title="compile all packages with gcc@11.3"
  compiler
  - toolchain: gcc
    spec: gcc@11.3
```

Sometimes two compiler toolchains are required, for example when using the `nvhpc` compilers, there are often dependencies that can't be built using the NVIDIA, or are better being built with GCC (for example `cmake`, `perl` and `netcdf-c`).
The example below uses the `nvhpc` compilers with gcc@11.3.

```yaml title="compile all packages with gcc@11.3"
  compiler
  - toolchain: llvm
    spec: nvhpc@22.7
  - toolchain: gcc
    spec: gcc@11.3
```

!!! note
    If more than one version of gcc has been installed, use the same version that was used to install `nvhpc`.

!!! warning
    As a rule, use a single compiler wherever possible - keep it simple!

    We don't test or support using two versions of gcc in the same toolchain.

### MPI

Stackinator can configure cray-mpich (CUDA, ROCM, or non-GPU aware) on a per-environment basis, by setting the `mpi` field in an environment.

!!! note
    Future versions of Stackinator will support OpenMPI, MPICH and MVAPICH when (and if) they develop robust support for HPE SlingShot 11 interconnect.

By default, MPI will not be configured in an environment:
```yaml title="environments.yaml: no MPI"
serial-env:
  mpi: null
```

To configure MPI without GPU support, set the `spec` field with an optional version:
```yaml title="environments.yaml: MPI without GPU support"
host-env:
  mpi:
    spec: cray-mpich@8.1.23
```

GPU-aware MPI can be configured by setting the optional `gpu` field to specify whether to support `cuda` or `rocm` GPUs:
```yaml title="environments.yaml: GPU aware MPI"
cuda-env:
  mpi:
    spec: cray-mpich
    gpu: cuda
  # ...
rocm-env:
  mpi:
    spec: cray-mpich
    gpu: rocm
  # ...
```

As new versions of cray-mpich are released with CPE, they are added to Stackinator.
The following versions of cray-mpich are currently provided:

|   cray-mpich  |   CPE     |   notes                  |
| :------------ | :-------- | :----------------------- |
|  8.1.25       | 23.03     | released 2023-02-26 **default** |
|  8.1.24       | 23.02     | released 2023-01-19  |
|  8.1.23       | 22.12     | released 2022-11-29  |
|  8.1.21.1     | 22.11     | released 2022-10-25  |
|  8.1.18.4     | 22.08     | released 2022-07-21  |

!!! alps
    All versions of cray-mpich in the table have been validated on Alps vClusters with Slingshot 11 and libfabric 1.15.2.

!!! note
    The `cray-mpich` spec is added to the list of package specs automatically, and all packages that use the virtual dependency `+mpi` will use this `cray-mpich`.

### specs

!!! warning "todo"

### packages

To specify external packages that should be used instead of building them, use the `packages` field.
For example, if the `perl`, `python@3` and `git` packages are build dependencies of an environment and the versions that are available in the base CrayOS installation are sufficient, the following spec would be specified:

```yaml title="environments.yaml: specif"
my-env:
  packages:
  - perl
  - git
```

!!! note
    If a package is not found, it will be built by Spack.

!!! note
    External packages specified in this manner will only be used when concretising this environment, and will not affect downstream users.

??? note "expand if you are curious how Stackinator configures Spack for packages"
    The following Spack call is used to generate `packages.yaml` in the Spack environment that 

    ```bash title="Makefile target that "
    packages.yaml:
        spack external find --not-buildable --scope=user perl git
    ```

### variants

To specify variants that should be applied to all package specs in the environment by default (unless overridden explicitly in a package spec), use the `variants` field.
For example, to concretise all specs in an environment that support MPI or CUDA and target A100 GPUs, the following `variants` could be set:

```yaml title="environments.yaml: variants for MPI and CUDA on A100"
cuda-env:
  variants:
    - +mpi
    - +cuda
    - cuda_arch=80
```

??? note "expand if you are curious how Stackinator configures Spack for variants"
    The above will add the following to the generated `spack.yaml` file used internally by Spack.

    ```yaml title="spack.yaml: packages spec generated for variants"
    spack:
      packages:
        all:
          variants:
          - +mpi
          - +cuda
          - cuda_arch=80
    ```

### views

!!! warning "todo"

### a full example

!!! warning "todo"

```yaml title="environments.yaml for simple PrgEnv-gnu setup"
gcc-host:
  compiler:
      - toolchain: gcc
        spec: gcc@11.3
  unify: true
  specs:
  - hdf5 +mpi
  - fftw +mpi
  mpi:
    spec: cray-mpich
    gpu: false
```

## Modules

Modules are generated for the installed compilers and packages by spack. The default module generation rules set by the version of spack specified in `config.yaml` will be used if no `modules.yaml` file is provided.

To set rules for module generation, provide a `module.yaml` file as per the [spack documentation](https://spack.readthedocs.io/en/latest/module_file_support.html).

To disable module generation, set the field `config:modules:False` in `config.yaml`.

## Custom Spack Packages

An optional package repository can be added to a recipe to provide new or customized Spack packages in addition to Spack's `builtin` package repository, if a `repo` path is provided in the recipe.

For example, the following `repo` path will add custom package definitions for the `hdf5` and `nvhpc` packages:

```
repo
└─ packages
   ├─ hdf5
   │  └─ package.py
   └─ nvhpc
      └─ package.py
```


Stackinator internally provides its own package repository with a custom package for `cray-mpich` package, which it puts in the `alps` namespace.
The `alps` repository is installed alongside the packages, and is automatically available to all Spack users that use the Spack stack as an upstream.

!!! warning
    Unlike Spack package repositories, any `repos.yaml` file in the `repo` path will be ignored and a warning will be issued.
    This is because the provided packages are added to the `alps` namespace.
