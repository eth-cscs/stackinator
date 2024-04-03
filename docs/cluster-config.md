# Cluster Configuration

Spack stacks are built on bare-metal clusters using a minimum of dependencies from the underlying system.
A cluster configuration is a directory with the following structure:

```
/path/to/cluster/configuration
├─ compilers.yaml   # system compiler
├─ packages.yaml    # external system packages
├─ concretiser.yaml
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

!!! warning
    Only use external dependencies that are strictly necessary:

    * the more dependencies, the more potential that software stacks will have to be rebuilt when the system is updated, and the more potential there are for breaking changes;
    * the external packages are part of the Spack upstream configuration generated with the Stack - you might be constraining the choices of downstream users.

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
│   ├─ compilers.yaml
│   ├─ packages.yaml
│   ├─ concretiser.yaml
│   └─ repos.yaml    # refers to ../site/repo
└─ site
   └─ repo           # the site wide repo
       └─ packages

## Package Precedence

If custom package definitions are provided for the same package in more than one location, Stackinator has to choose which definition to use.

There following precedence is applied, in descending order of precidence:
* packages defined in the (optional) `repo` path in the [recipe](recipes.md#custom-spack-packages)
* packages defined in the (optional) site repo(s) defined in the `repo/repos.yaml` file of cluster configuration (documented here)
* packages provided by Spack (in the `var/spack/repos/builtin` path)

As of Stackinator v4, the definitions of some custom repositories (mainly CSCS' custom cray-mpich and its dependencies) was removed from Stackinator, and moved to the the site configuration
