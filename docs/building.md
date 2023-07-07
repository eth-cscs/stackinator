# Building Spack Stacks

Once a stack has been [configured](configuring.md) using `stack-config`, it's time to build the software stack.

## How to Build

The configuration generates a build path, with a top-level `Makefile` that performs the build.

```
# configure the build
stack-config --build $BUILD_PATH ...

# perform the build
cd $BUILD_PATH
env --ignore-environment PATH=/usr/bin:/bin:`pwd`/spack/bin make modules store.squashfs -j32
```

The call to `make` is wrapped with with `env --ignore-env` to unset all environment variables, to improve reproducability of builds.

Build times for stacks typically vary between 30 minutes to 3 hours, depending on the specific packages that have to be built.
Using [build caches](build-caches.md) and building in shared memory (see below) are the most effective methods to speed up builds.

## Where to Build

Spack detects the CPU μ-arch that it is being run on, and configures the packages to target it.
In order to ensure the best results, build the stack on a compute node with the target architecture, not a login node.

!!! alps
    Alps vClusters often have different CPU μ-arch on login nodes (zen2) and compute nodes (zen3).

Build times can be signficantly reduced by creating the build path in memory, for example in `/dev/shm/$USER/build`, so that all of the dependencies are built and stored in memory, instead of on a slower shared file system.

!!! alps
    All of the Cray EX nodes on Alps have 512 GB of memory, which is sufficient for building software stacks, though it is important that the memory is cleaned up, preferably via an automated policy.

!!! warning
    Take care to remove the build path when building in shared memory -- otherwise it will reduce the amount of memory available for later users of the node, because some clusters do not automatically clean up `/dev/shm` on compute nodes -- and `/dev/shm` is only cleared on login nodes when they are reset.

