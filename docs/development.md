# Development

This page is for developers and maintainers of Stackinator.

## Debug environment

Debugging stack builds can be challenging, because the build uses an environment with paths mounted and remounted using bwrap and different environment variables than the calling shell.

A helper script that will open a new shell with the same environment as the stack build is generated in the build path.
The script, `stack-debug.sh`, can be sourced to start the new bash shell:

```bash
user@hostname:/dev/shm/project-build > source ./stack-debug.sh
build-env >>>
```

The new shell has `spack` in its path, and has the store path mounted at the environment's mount point.
To finish debugging, exit the shell with `exit` or ctrl-d.

