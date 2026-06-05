# Mirrors and Build Caches

Spack can use *mirrors* and *caches* to speed up image builds and to build on systems with limited or no internet access.
They are configured in a single `mirrors.yaml` file in the [system configuration](cluster-config.md).

A `mirrors.yaml` can describe four kinds of entry, each optional and each documented below:

| Entry | Count | Purpose |
|-------|-------|---------|
| [`buildcache`](#build-cache)   | one  | binary cache of built packages (the big build-time speed up) |
| [`bootstrap`](#bootstrap-mirror) | one  | mirror used to bootstrap Spack itself |
| [`sourcemirror`](#source-mirrors) | many | read-only mirrors that provide package sources |
| [`sourcecache`](#source-cache)  | one  | writable local cache that fills with sources as you build |

A complete example:

```yaml title="mirrors.yaml"
buildcache:
  url: file:///capstor/scratch/team/uenv-cache
  private_key: $SCRATCH/.keys/spack-push-key.gpg
  mount_specific: true
bootstrap:
  url: https://bootstrap.spack.io
sourcemirror:
  mirror1:
    url: https://example.com/spack-sources
sourcecache:
  path: /capstor/scratch/$USER/spack-sources
```

To stop using any entry, remove (or comment out) it from `mirrors.yaml`.

## Build cache

A build cache is a binary cache of built packages.
Reusing binaries instead of rebuilding from source is roughly a 10x speed up — the difference between a 3 minute and a 30 minute image build — so a build cache is essential if you build images regularly.

During a build Spack fetches packages from the cache when it can, and signs and pushes any package it has to build itself, so the cache improves over time.

```yaml title="mirrors.yaml"
buildcache:
  url: file:///capstor/scratch/team/uenv-cache
  private_key: $SCRATCH/.keys/spack-push-key.gpg
```

| Field | Required | Description |
|-------|----------|-------------|
| `url`            | yes | location of the cache (a `file://` path, or an `http(s)://`, `s3://` or `oci://` URL) |
| `private_key`    | no  | PGP key used to sign and push packages (see [Keys](#keys)); omit for a read-only cache |
| `public_key`     | no  | PGP key used to verify downloaded packages |
| `name`           | no  | name Spack registers the mirror under (default `buildcache`) |
| `mount_specific` | no  | store the cache in a per-mount-point sub-directory (default `false`) |

### Read-only build cache

Omit `private_key` to configure a read-only cache: Spack fetches packages from it but never signs or pushes anything back.
This is useful for consuming a shared team cache that you are not permitted to write to.

```yaml title="mirrors.yaml"
buildcache:
  url: file:///capstor/scratch/team/uenv-cache
```

### `mount_specific`

Spack binaries embed the install prefix (the image's mount point), so binaries built for `/user-environment` cannot be reused at a different mount point.
Set `mount_specific: true` to append the mount point to the cache URL, giving each mount point its own sub-directory and avoiding relocation issues:

```yaml
buildcache:
  url: file:///capstor/scratch/team/uenv-cache
  private_key: $SCRATCH/.keys/spack-push-key.gpg
  mount_specific: true   # packages stored under .../uenv-cache/user-environment
```

### Creating a build cache

A build cache needs an empty directory and a PGP signing key:

```bash
# 1. create the cache directory
mkdir -p $SCRATCH/uenv-cache

# 2. generate and export a signing key
spack gpg create <name> <e-mail>
spack gpg export --secret $SCRATCH/.keys/spack-push-key.gpg
```

See [Keys](#keys) for where to store the key.

### Force pushing

Packages are pushed to the cache after each environment builds successfully; nothing is pushed if a build fails.
When iterating on a recipe with failing builds, force-push everything built so far with the `cache-force` target:

```bash
env --ignore-environment PATH=/usr/bin:/bin:`pwd -P`/spack/bin make cache-force
```

## Bootstrap mirror

Spack bootstraps some of its own dependencies (such as the `clingo` concretizer) on first use.
A bootstrap mirror lets it do this without reaching the internet — useful on air-gapped systems.

```yaml title="mirrors.yaml"
bootstrap:
  url: https://bootstrap.spack.io
```

| Field | Required | Description |
|-------|----------|-------------|
| `url`        | yes | location of the bootstrap mirror |
| `public_key` | no  | PGP key used to verify the bootstrap binaries |

## Source mirrors

Source mirrors provide package **source** archives, and are read-only: Spack fetches sources from them but never writes to them.
Use them to build on air-gapped systems — populate a mirror on a connected system, mount it read-only, and Spack will fetch sources from it.
Any number of source mirrors can be listed; Spack searches them in order.

```yaml title="mirrors.yaml"
sourcemirror:
  internal:
    url: https://mirror.example.com/spack-sources
  scratch:
    url: file:///capstor/scratch/team/spack-sources
```

| Field | Required | Description |
|-------|----------|-------------|
| `url`        | yes | location of the source mirror |
| `public_key` | no  | PGP key used to verify sources |

Populate a source mirror on an internet-connected system with Spack:

```bash
spack mirror create --directory /path/to/mirror --all
```

## Source cache

A source cache is a single, **writable** local directory that Spack fills as it downloads sources.
On internet-connected systems Spack checks the cache first; on a miss it downloads the source and stores it, so later builds reuse it and download times shrink over time.

Unlike a source mirror it needs no key, is written to automatically, and is created on demand.

```yaml title="mirrors.yaml"
sourcecache:
  path: /capstor/scratch/$USER/spack-sources
```

| Field | Required | Description |
|-------|----------|-------------|
| `path` | yes | absolute path to a local directory (environment variables are expanded) |

## Keys

The `private_key` and `public_key` fields accept either:

* a **path** — absolute, or relative to the system configuration directory; or
* a **base64-encoded key** inlined directly in `mirrors.yaml`.

```yaml
buildcache:
  url: file:///capstor/scratch/team/uenv-cache
  private_key: $SCRATCH/.keys/spack-push-key.gpg     # a path
  public_key: mQINBGm4GvsBEACTyzQF...==              # inline base64
```

Generate a key with Spack, and keep the secret key somewhere private:

```bash
mkdir $SCRATCH/.keys && chmod 700 $SCRATCH/.keys
spack gpg create <name> <e-mail>
spack gpg export --secret $SCRATCH/.keys/spack-push-key.gpg
chmod 600 $SCRATCH/.keys/spack-push-key.gpg
```

See the [Spack documentation](https://spack.readthedocs.io/en/latest/getting_started.html#gpg-signing) for more on GPG keys.

!!! failure "Don't use `$HOME`"
    The build remounts `~` as a tmpfs, so keys under `$HOME` are not visible during the build and Spack will fail to read them. Use scratch storage instead.

## Legacy `--cache` option

Before `mirrors.yaml`, a build cache was configured with a separate `cache.yaml` file passed to `stack-config` via `-c/--cache`:

```yaml title="cache.yaml"
root: $SCRATCH/uenv-cache
key:  $SCRATCH/.keys/spack-push-key.gpg
```

```bash
stack-config -b $build -r $recipe -s $system -c cache.yaml
```

This is **deprecated** and equivalent to a single `buildcache` entry (with `mount_specific: true`). Prefer configuring the build cache in `mirrors.yaml`.

Setting `key: null` configures a read-only cache that Spack fetches from but never pushes to.
