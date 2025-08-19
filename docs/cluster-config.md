# Cluster Configuration

Spack stacks are built on bare-metal clusters using a minimum of dependencies from the underlying system.
A cluster configuration is a directory with the following structure:

```
/path/to/cluster/configuration
├─ packages.yaml    # external system packages
├─ network.yaml     # configuration options for network libraries
└─ repos.yaml       # optional reference to additional site packages
```

The configuration is provided during the [configuration](configuring.md) step with the `--system/-s` flag.
The following example targets the Clariden system at CSCS:

```bash
git clone git@github.com:eth-cscs/alps-cluster-config.git
stack-config --system ./alps-cluster-config/clariden --recipe <recipe path> --build <build path>
```

!!! alps
    The CSCS _official configuration_ for vClusters on Alps are maintained in a GitHub repository [github.com/eth-cscs/alps-cluster-config](https://github.com/eth-cscs/alps-cluster-config).

    Software stacks provided by CSCS will only use the official configuration, and support will only be provided for user-built stacks that used the official configuration.

If there are additional system packages that you want to use in a recipe, consider adding a `packages.yaml` file to the recipe, in which you can define additional external packages.

!!! warning "Only use external dependencies that are strictly necessary"
    * the more dependencies, the more potential that software stacks will have to be rebuilt when the system is updated, and the more potential there are for breaking changes;
    * the external packages are part of the Spack upstream configuration generated with the Stack - you might be constraining the choices of downstream users.

[](){#ref-cluster-config-network}
### Configuring MPI and network libraries: `network.yaml`

The `network.yaml` file contains two high level fields:

```yaml title="network.yaml"
mpi:
    cray-mpich:
        specs: [... default packages to add to the network stack ...]
    openmpi:
        specs: [... default packages to add to the network stack ...]
# standard Spack packages.yaml for packages
packages:
    libfabric: ...
    openmpi:   ...
```

??? example "example `network.yaml` for grace hopper"
    * The `specs` field for `mpi:cray-mpich:specs` and `mpi:openmpi:specs` fields set different default `libfabric` for the respective MPI distributions.
    * By default `packages:cray-mpich` and `packages:openmpi` add the `+cuda` variant as a preference to build with cuda support by default on the Grace-Hopper nodes.
        * This can be overriden by adding `~cuda` to the spec in `network:mpi` in your recipe.
    * The version of `libfabric` on the system is `1.22.0`, but it is set as buildable so that it can be built from source by Spack if a different (more recent) version is selected in a recipe.
    * A combination of `require` and `prefer` are used in the `packages` definitions to enforce settings and set defaults, respectively.

    ```yaml title="network.yaml"
    mpi:
      cray-mpich:
        specs: ["libfabric@1.22"]
      openmpi:
        specs: ["libfabric@2.2.0"]
    packages:
      # adding a variant to the variants field of a package
      #   e.g. packages:openmpi:variants
      # is not strong enough: if that variant does not exist it simply will be ignored with no error message
      openmpi:
        buildable: true
        require:
          - 'schedulers=slurm'
          - 'fabrics=cma,ofi,xpmem'
          - '+internal-pmix'
          - '+cray-xpmem'
        prefer:
          - '+cuda'
        variants: []
      cray-mpich:
        buildable: true
        prefer:
          - '+cuda'
          - '@8.1.32'
      libfabric:
        buildable: true
        externals:
        - spec: libfabric@1.22.0 fabrics=cxi,rxm,tcp
          prefix: /opt/cray/libfabric/1.22.0/
        version: ["git.v2.2.0=main"]
        require: fabrics=cxi,rxm,tcp
      libcxi:
        version: ["git.be1f7149482581ad589a124e5f6764b9d20d2d45=main"]
      cxi-driver:
        version: ["git.08deb056fac4ca8b0d3d39b5f7cc0dad019ee266=main"]
      cassini-headers:
        version: ["git.59b6de6a91d9637809677c50cc48b607a91a9acb=main"]
    ```

## Site and System Configurations

The `repo.yaml` configuration can be used to provide a list of additional Spack package repositories to use on the target system.
These are applied automatically to every recipe built on the target cluster.

To provide site wide defaults, links to additional package repositories can be provdided in the the cluster definition.
For example, the following definition would link to a set of site-wide package definitions

```yaml
repos:
- ../site/repo
```

The paths are always interpretted as relative to the system configuration.
This is designed to make it encourage putting cluster definitions and the site description in the same git repository.

```
/path/to/cluster-configs
├─ my_cluster
│   ├─ packages.yaml
│   ├─ network.yaml
│   └─ repos.yaml    # refers to ../site/repo
└─ site
   └─ repo           # the site wide repo
       └─ packages
```

!!! alps
    The site wide package definitions on Alps are maintained in the [alps-cluster-config repository](https://github.com/eth-cscs/alps-cluster-config/tree/master/site/repo).

## Package Precedence

If custom package definitions are provided for the same package in more than one location, Stackinator has to choose which definition to use.

The following precedence is applied, where 1 has higher precedence than 2 or 3:

1. packages defined in the (optional) `repo` path in the [recipe](recipes.md#custom-spack-packages)
2. packages defined in the (optional) site repo(s) defined in the `repo/repos.yaml` file of cluster configuration (documented here)
3. packages provided by Spack (in the `var/spack/repos/builtin` path)

As of Stackinator v4, the definitions of some custom repositories (mainly CSCS' custom cray-mpich and its dependencies) was removed from Stackinator, and moved to the the site configuration
