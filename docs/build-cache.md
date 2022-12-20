# Build Caches

Building a full environment from scratch takes anywhere from 20 minutes to 3 hours, depending on the number and dependencies of the requested packages.

The stacks are designed to be built in one-shot - incremental development and builds of an environment are not guaranteed to work, and building from scratch is the only way to generate a reproducable environment.

The tool supports using spack binary caches to reduce build times, particularly incremental builds.

## Installing from build caches

For Hohgant a default mirror is provided that contains.

> **Note**
> The binary packages in the binary caches are not relocatable.
> The default binary cache assumes that they have been built for the `/user-environment` mount point.
> If you are using a different mount point, disable the binary cache or provide your own.

To disable the cache

## Pushing to a cache

By default, a binary cache is used only for downloading binary packages.
To push packages to the cache for use in later builds, provide the gpg private key used to sign packages in the build-cache.

This is done by setting `mirror-key` in the recipe `config.yaml`:
`config.yaml`:

```yaml
config:
  mirror:
    # The key for signing packages for pusing to the build cache
    # If not provided, not pacakges will be pushed to the build cache
    key: /tmp/spack-push-key.gpg
    # Toggle to disable
    enable: false
```

### Generating the key

To generate the key file, from the spack installation that was used to build the cache use `spack gpg export --private`.

```bash
# create a key
spack gpg create ...

# perform actions that push to the 
spack build-cache create --rebuild-index ...
spack gpg export --private spack-push-key.gpg
```

See the [spack documentation](https://spack.readthedocs.io/en/latest/getting_started.html#gpg-signing) for more information about GPG keys.
