# Interfaces

Software stacks offer a choice of interfaces that can be presented to users.

## Spack Upstream

Every stack can be used as a Spack upstream for users of Spack on the system.
This means that users can access all of the software packages and custom recipes provided by a software Spack directly in their Spack configuration.

The installation contains a [custom configuration scope](https://spack.readthedocs.io/en/latest/configuration.html#custom-scopes) in the `config` sub-directory, and additional information about custom Spack packages in the `repo` sub-directory.
For example, the Spack configuration is in the following files when a stack has been installed at the default `/user-environment` mount point:
```
/user-environment
├─ config
│  ├─ repos.yaml
│  ├─ packages.yaml
│  └─ upstreams.yaml
└─ repo
   ├─ repo.yaml
   └─ packages
      └─ cray-mpich
         └─ package.py
```

Notes on the configuration files:

* `upstream.yaml`: Registers the spack packages installed in the Spack stack so that they will be found by the downstream user when searching for packages:
    ```yaml
    upstreams:
      system:
        install_tree: /user-environment
    ```
* `packages.yaml`: refers to the external packages that were used to configure the recipe: both the defaults in the cluster configuration, and any additional packages that were set in the recipe.
* `repos.yaml`: points to the custom Spack repository:
    ```yaml
    repos:
    - /user-environment/repo
    ```

End users can use the Spack stack in their Spack installations in a variety of ways, including:
```bash
# set an environment variable
export SPACK_SYSTEM_CONFIG_PATH=/user-environment/config

# pass on command line to Spack
spack --config-scope /user-environment/config ...
```

See the [Spack documentation](https://spack.readthedocs.io/en/latest/configuration.html) for the diverse ways that custom configurations can be used.

The `repo` path contains the custom `cray-mpich` package configuration.
If the stack recipe provided additional custom packages, these will also be in sub-directories of `$install_path/repo/packages`

## Modules

Module files can be provided as an optional interface, for users that and use-cases that prefer or require them.

If modules are available, the generated module files are in the `modules` sub-directory of the installation path, and end users can make them available via `module use`:

```bash
# make the modules available
module use /user-environment/modules

# list the available moduels
module avail

-------------------------- /user-environment/modules --------------------------
   cmake/3.26.3    gcc/11.3.0       libtree/3.1.1               python/3.10.10
   cray-mpich      hdf5/1.14.1-2    osu-micro-benchmarks/5.9    tree/2.1.0
```

## Environment Views

File system views are an optional way to provide the software from an environment in a directory structure similar to `/usr/local`, based on Spack's [filesystem views](https://spack.readthedocs.io/en/latest/environments.html#filesystem-views).
See the [recipe documentation](recipes.md#views) for details on how to configure views.

The views are created in the `env` path of the installation.
As an example, given two views named `default` and `no-python` for an stack installed in the standard `/user-environment` location, then two directory trees named after the views are generated in `/user-environment/env`:

```
/user-environment
└─ env
   ├─ default
   │  ├─ bin
   │  ├─ lib
   │  ├─ ...
   │  └─ activate.sh
   └─ no-python
      ├─ bin
      ├─ lib
      ├─ ...
      └─ activate.sh
```

The `activate.sh` script in each view can be used to load the view by setting environment variables like `PATH`, `LD_LIBRARY_PATH`, `CPATH` etc.

```bash
source /user-environment/env/no-python/activate.sh
```

!!! note
    Meta data about the environment views provided by a Spack stack is provided in the file `meta/env.json`.

