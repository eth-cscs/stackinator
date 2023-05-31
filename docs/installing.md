# Installing Stacks

The installation path of the software stack is set when the stack is configured.

The default location for a recipe is set in the `store` field of `config.yaml` in the recipe:
```yaml title='config.yaml'
name: best-stack-ever
store: /user-environment
spack:
  commit: releases/v0.20
  repo: https://github.com/spack/spack.git
```

The installation path can be overridden using the `--mount/-m` flag to `stack-config`.
The software is built using rpaths hard-coded to the installation path, which simplifies dynamic linking  (`LD_LIBRARY_PATH` does not have to be set during run time).

!!! alps
    For deployment on Alps, stacks should use the standard `/user-environment` mount point.

!!! warning
    Environments built for one mount point should not be mounted at a different location.
    If a new mount point is desired, rebuild the stack for the new mount point.

## Installing the software

Running gmake to build the environment generates two versions of the software stack in the build path:
```
build_path
├─ store
└─ store.squashfs
```

### Shared file system installation

The `store` sub-directory contains the full software stack installation tree.

!!! note
    The "simplest" method for installing the software stack, that does not require installing additional tools to use the stack, is to copy the contents of `store` to the installation path.


### SquashFS installation

The `store.squashfs` file is a compressed [SquashFS](https://tldp.org/HOWTO/SquashFS-HOWTO/whatis.html) image of the contents of the `store` path.
This can be mounted at runtime using [`squashfs-mount`](https://github.com/eth-cscs/squashfs-mount) or [Slurm plugins](https://github.com/eth-cscs/slurm-uenv-mount/), or mounted by a system-administrator using [`mount`](https://man7.org/linux/man-pages/man2/mount.2.html), in order the to take advantage of the benefits of SquashFS over shared file systems.
