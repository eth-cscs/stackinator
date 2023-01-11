# Build Caches

Building a full environment from scratch takes anywhere from 20 minutes to 3 hours, depending on the requested packages.
The stacks are designed to be built in one-shot. Incremental development and builds are possible, however they not guaranteed to work, and building from scratch is the only way to generate a reproducable environment.

The tool supports using spack build caches to reduce build times.

## Installing from build caches

To use a build cache provide a `mirror.yaml` file in the recpie path. The `mirror.yaml` file is a standard [Spack mirror file](https://spack.readthedocs.io/en/latest/mirrors.html).

> **Note**
> Binary caches are 
> If you don't want to use the cache, it can be disabled -- see Pushing to a Cache below.

> **Note**
> A default read-only build cache is provided by default on Hohgant.
> If you don't want to use the cache, it can be disabled -- see Pushing to a Cache below.

### Hohgant

For Hohgant a default mirror is used.

> **Note**
> The binary packages in the Hohgant build cache are not relocatable, and are
> built for the `/user-environment` mount point. If you are using a different
> mount point, disable the build cache or provide your own.

To disable the build cache in a recipe, set `config:mirror:enable` in `config.yaml`:

```yaml
config:
  mirror:
    # Toggle to disable using mirror.yaml, if provided.
    # Default value is true.
    enable: false
```

## Pushing to a Cache

By default, a build cache is used only for downloading binary packages.
To push packages to the cache for use in later builds, provide the gpg private key used to sign packages in the build-cache, by setting the `mirror-key` field in `config.yaml`:

```yaml
config:
  mirror:
    # The key for signing packages for pushing to the build cache
    # If not provided, build caches will be read-only.
    key: /tmp/spack-private-key.gpg
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
