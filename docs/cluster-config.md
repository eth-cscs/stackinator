# Cluster Configuration

Spack stacks are built on bare-metal clusters using a minimum of dependencies from the underlying system.
A cluster configuration is a directory with the following structure:

```
/path/to/cluster/configuration
├─ compilers.yaml   # system compiler
├─ packages.yaml    # external system packages
└─ concretiser.yaml
```

The CSCS "official configuration" for vClusters on Alps are maintained in a GitHub repository [github.com/eth-cscs/alps-cluster-config](https://github.com/eth-cscs/alps-cluster-config).
 `--system/-s` flag that points to a directory with the following structure:

```bash
git clone git@github.com:eth-cscs/alps-cluster-config.git
stack-config --system ./alps-cluster-config/clariden --recipe <recipe path> --build <build path>
```

!!! alps
    Software stacks provided by CSCS will only use the official configuration, and support will only be provided for user-built stacks that used the official configuration.

If there are additional system packages that you want to use in a recipe, consider adding a `packages.yaml` file to the recipe, in which you can define additional external packages.

!!! warning
    Only use external dependencies that are strictly necessary:

    * the more dependencies, the more potential that software stacks will have to be rebuilt when the system is updated, and the more potential there are for breaking changes;
    * the external packages are part of the Spack upstream configuration generated with the Stack - you might be constraining the choices of downstream users.

