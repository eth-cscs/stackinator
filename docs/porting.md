[](){#ref-porting}
# Porting recipes to Spack 1.0

This guide covers the main differences between version 1 and version 2 of the Stackinator recipe format.
Follow it to update uenv recipes that were created for Spack v0.23 and earlier to target Spack 1.0 using Stackinator 6.

## `config.yaml`

First, add `version: 2` as a specification in the config.yaml file to tell Stackinator that the recipe is in the new format.

Spack 1.0 moved the `builtin` package definition repository from the Spack main repository to its own standard location, which is now versioned separately.
This change is reflected in the config file

!!! example
    === "Stackinator 5"

        ```yaml title="config.yaml"
        name: prgenv-gnu
        store: /user-environment
        spack:
          repo: https://github.com/spack/spack.git
          commit: releases/v0.23
        modules: true
        description: "HPC development tools for building MPI applications with the GNU compiler toolchain"
        ```


    === "Stackinator 6"

        ```yaml title="config.yaml"
        name: prgenv-gnu
        store: /user-environment
        spack:
          repo: https://github.com/spack/spack.git
          commit: releases/v1.0
          packages:         # (1)
            repo: https://github.com/spack/spack-packages.git
            commit: releases/v2025.07
        modules: true
        description: "HPC development tools for building MPI applications with the GNU compiler toolchain"
        version: 2          # (2)
        ```

        1. the `packages` field is new.
        1. don't forget to specify version 2.

## `compilers.yaml`

The format of the `compilers.yaml` file has been simplified, and support for llvm has been added.

There is no bootstrap compiler, and only a single version of `gcc`, `nvhpc` or `llvm` is allowed.
Because of this, the compiler description is greatly streamlined.

!!! example "a gcc based uenv"
    This uenv uses `gcc@13` as the only compiler.

    === "Stackinator 5"

        ```yaml title="compilers.yaml"
        bootstrap:
          spec: gcc@12.3
        gcc:
          specs:
          - gcc@13
        ```


    === "Stackinator 6"

        ```yaml title="compilers.yaml"
        gcc:
          version: "13"
        ```

!!! example "a gcc and nvhpc based uenv"
    This uenv uses `gcc@13` and `nvhpc@25.1`.

    === "Stackinator 5"

        ```yaml title="compilers.yaml"
        bootstrap:
          spec: gcc@12.3
        gcc:
          specs:
          - gcc@13.2
        llvm:
          requires: gcc@13
          specs:
          - nvhpc@25.1
        ```

    === "Stackinator 6"

        ```yaml title="compilers.yaml"
        gcc:
          version: "13"
        nvhpc:
          version: "25.1"
        ```

## `environments.yaml`

The main change in `environments.yaml` is how the compiler toolchain is specified.
The compilers are provided as a list, without version information.

!!! example "a gcc based uenv"
    This uenv uses `gcc@13` as the only compiler.

    === "Stackinator 5"

        ```yaml title="environments.yaml"
        compiler:
        - toolchain: gcc
          spec: gcc
        ```

    === "Stackinator 6"

        ```yaml title="environments.yaml"
        compiler: [gcc]
        ```

!!! example "a gcc and nvhpc based uenv"
    This uenv uses `gcc@13` and `nvhpc@25.1`.

    === "Stackinator 5"

        ```yaml title="environments.yaml"
        compiler:
        - toolchain: gcc
          spec: gcc
        - toolchain: llvm
          spec: nvhpc
        ```

    === "Stackinator 6"

        ```yaml title="environments.yaml"
        compiler: [gcc, nvhpc]
        ```

Avoid specifying the compiler to use for `cray-mpich`, because this conflicts with the new Spack specification format.

!!! example "do not specify compiler to use for cray-mpich"
    This uenv uses `gcc@13` and `nvhpc@25.1`.

    === "Stackinator 5"

        ```yaml title="environments.yaml"
        mpi:
          spec: cray-mpich@8.1.30%nvhpc
          gpu: cuda
        ```

    === "Stackinator 6"

        ```yaml title="environments.yaml"
        mpi:
          spec: cray-mpich@8.1.30
          gpu: cuda
        ```

!!! note
    The method for specifying MPI and networking software stacks will be updated to give you more control over how MPI is compiled before Stackinator 6 is released.

    Typically you want to install `cray-mpich` with `nvhpc` to support building Fortran applications with the `nvfortran` compiler.
    You can force this by adding `%fortran=nvhpc` to one of the specs in your environment that is compiled with Fortran, e.g.
    ```yaml title="environments.yaml
    specs:
      - hdf5+mpi+hl+fortran %fortran=nvhpc
    ```
    This will transitively require that `cray-mpich` be installed using `nvhpc`.

## `modules.yaml`

There are no changes required to the modules.yaml definition.

## repo

If your recipe contains custom package definitions in a , you may have to update these to support Spack 1.0.

If the package was based on one from Spack, have a look at the updated package definition for Spack 1.0.
You can also look at changes that were made to similar custom packages in [alps-uenv](https://github.com/eth-cscs/alps-uenv) recipes when they were updated to Stackinator 6.0
