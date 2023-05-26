# Recipes

A recipe is a description of all of the compilers and software packages to be installed, along with configuration of modules and environment scripts the stack will provide to users.
A recipe is comprised of the following yaml files in a directory:

* `config.yaml`: common configuration for the stack.
* `compilers.yaml`: the compilers provided by the stack.
* `environments.yaml`: environments that contain all the software packages.
* `modules.yaml`: _optional_ module generation rules
    * follows the spec for (spack mirror configuration)[https://spack.readthedocs.io/en/latest/mirrors.html]
* `packages.yaml`: _optional_ package rules.
    * follows the spec for (spack package configuration)[https://spack.readthedocs.io/en/latest/build_settings.html]
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
* `mirrors`: _optional_ configure use of build caches, see [build cache documentation](docs/build-cache.md).
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
