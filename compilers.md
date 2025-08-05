TODO:
- remove the requirement (which is overly broad and blocks us from using `requires` below)
    - link: [github.com/eth-cscs/alps-cluster-config](https://github.com/eth-cscs/alps-cluster-config/blob/main/site/spack_repo/alps/packages/cray_mpich/package.py#L80-L85)

There are two ways to set up a multi compiler toolchain

- set `spack:packages:all:prefer` to prefer the first compiler (trying to make it select compilers doesn't have any effect)
    - then add `%fortran=nvhpc` to individual packages
    - if applied to one package, this will propogate to other fortran packages (probably via nvhpc)
    - note that applying this to `cray-mpich` does the trick
- set `spack:packages:all:require;-one_of` to hard-code the specific `c`, `cxx` and `fortran` compilers (see below)
    - then the user does not override this on individual specs

The best spot to specify this is probably in the `compiler` field of `environments.yaml` in a recipe, e.g.:

```
  compiler:
        c: gcc
        cxx: gcc
        fortran: nvhpc
    mode: # one of prefer, require
```
This would be easy to match to `'%[when=%c] c=gcc %[when=%cxx] cxx=gcc %[when=%fortran] fortran=nvhpc'`, and push into `require:one_of`

Note the docs on toolchains:
https://spack.readthedocs.io/en/latest/advanced_topics.html#defining-and-using-toolchains

note from the PR suggests something like:
```
packages:
  all:
    requires:
    - spec: %[virtuals=c] gcc
      when: %c
    - spec: %[virtuals=cxx] gcc
      when: %cxx
    - spec: %[virtuals=fortran] nvhpc
      when: %fortran
```
The syntax in the PR might a bit out of date, but we could aim to generate similar text?
Or, we can create a `spack:toolchain:` field that defines a toollchain, and use that toolchain everywhere.


```yaml
spack:
  specs: []
  packages:
    all:
      # pick one of the following (require will force everything - no need to override anything
      require:
      - one_of: ['%[when=%c] c=gcc %[when=%cxx] cxx=gcc %[when=%fortran] fortran=nvhpc']
      # it is not clear whether this actually does anything (other than subtly pushing spack towards gcc)
      # we find that it setting, e.g., fortran=nvhpc, changes concretisation, but does not actaully use nvfortran
      # with this option, users can 
      prefer: ['%[when=%c] c=gcc %[when=%cxx] cxx=gcc %[when=%fortran] fortran=gcc']
      variants: ['+mpi', '+cuda', 'cuda_arch=90']
    mpi:
      require: ...
```
