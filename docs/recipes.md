# Recipes

## Configuration

## Compilers

## Environments

## Modules

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
