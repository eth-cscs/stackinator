# Mirrors and Build Caches

Spack can use *mirrors* and *caches* to speed up image builds and to build on systems with limited or no internet access.

They are configured in a single YAML file passed to `stack-config` using the `--mirror` flag:

```bash
stack-config -b $build -r $recipe -s $system --mirror mirrors.yaml
```

The file is not part of the [system configuration](cluster-config.md): mirror locations are usually specific to the person running the build, so each invocation provides its own.

A `mirrors.yaml` can describe five kinds of entry, each optional and each documented below:

| Entry | Count | Purpose |
|-------|-------|---------|
| [`buildcache`](#build-cache)   | one  | binary cache of built packages (the big build-time speed up) |
| [`bootstrap`](#bootstrap-mirror) | one  | mirror used to bootstrap Spack itself |
| [`sourcemirror`](#source-mirrors) | many | read-only mirrors that provide package sources |
| [`sourcecache`](#source-cache)  | one  | writable local cache that fills with sources as you build |
| [`concretizer`](#concretizer-cache)  | one  | writable local cache that persists concretization results |

!!! example
    ```yaml title="mirrors.yaml"
    buildcache:
      url: file:///capstor/scratch/team/uenv-cache
      private_key: /capstor/scratch/bobsmith/.keys/spack-push-key.gpg
      mount_specific: true
    bootstrap:
      url: https://bootstrap.spack.io
    sourcemirror:
      # more than one source mirror can be configred.
      netmirror:
        url: https://example.com/spack-sources
      localmirror:
        url: file://scratch/group15/spack-sources
    sourcecache:
      path: /capstor/scratch/bobsmith/spack-sources
    concretizer:
      path: /capstor/scratch/bobsmith/spack-concretizer
    ```

!!! note
    Paths inside the file (such as relative gpg key paths) are resolved relative to the directory containing the `mirrors.yaml`, so a self-contained mirror directory (the `mirrors.yaml` plus its keys) can be moved around freely.


To stop using any entry, remove (or comment out) it from `mirrors.yaml`.

## Build cache

A build cache is a binary cache of built packages.
Reusing binaries instead of rebuilding from source is roughly a 10x speed up — the difference between a 3 minute and a 30 minute image build — so a build cache is essential if you build images regularly.

During a build Spack fetches packages from the cache when it can, and signs and pushes any package it has to build itself, so the cache improves over time.

```yaml title="mirrors.yaml"
buildcache:
  url: file:///capstor/scratch/team/uenv-cache
  private_key: /capstor/scratch/bobsmith/.keys/spack-push-key.gpg
```

| Field | Required | Description |
|-------|----------|-------------|
| `url`            | yes¹ | location of the cache (a `file://` path, or an `http(s)://`, `s3://` or `oci://` URL) |
| `private_key`    | no  | PGP key used to sign and push packages (see [Keys](#keys)); omit for a read-only cache |
| `public_key`     | no  | PGP key used to verify downloaded packages |
| `name`           | no  | name Spack registers the mirror under (default `buildcache`) |
| `mount_specific` | no  | store the cache in a per-mount-point sub-directory (default `false`) |
| `fetch` / `push` | no¹ | separate read/write [connections](#connections-and-authentication), used instead of a single `url` |
| `binary`         | no  | the cache holds binary packages (default `true`) |
| `source`         | no  | the cache also holds package sources (default `false`) |
| `signed`         | no  | whether Spack signs/verifies binaries with GPG (passed through to Spack) |
| `autopush`       | no  | Spack pushes each package as soon as it is installed (passed through to Spack) |

¹ Give either a top-level `url` *or* explicit `fetch`/`push` connections — see [Connections and authentication](#connections-and-authentication).

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
  private_key: /capstor/scratch/bobsmith/.keys/spack-push-key.gpg
  mount_specific: true   # packages stored under .../uenv-cache/user-environment
```

### Creating a build cache

A build cache needs an empty directory and a PGP signing key:

```bash
# 1. create the cache directory
mkdir -p /capstor/scratch/bobsmith/uenv-cache

# 2. generate and export a signing key
spack gpg create <name> <e-mail>
spack gpg export --secret /capstor/scratch/bobsmith/.keys/spack-push-key.gpg
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

No key is needed: bootstrap binaries are verified by their sha256 sum, not by a GPG signature.

The `url` can take two forms.

**A local bootstrap mirror directory** (recommended) — a directory created with `spack bootstrap mirror`, which contains its own `metadata/sources` and `metadata/binaries` descriptors:

```yaml title="mirrors.yaml"
bootstrap:
  url: /capstor/scratch/team/bootstrap-mirror
```

Stackinator references the mirror's own metadata directly, so both source and binary bootstrapping work. Create one on a connected system and copy it across:

```bash
spack bootstrap mirror --binary-packages /capstor/scratch/team/bootstrap-mirror
```

**A remote url** — `https://`, `s3://` or `oci://`:

```yaml title="mirrors.yaml"
bootstrap:
  url: https://bootstrap.example.com/mirror
```

A remote mirror supports **source** bootstrapping only; remote binary bootstrapping is not supported (it needs the per-package metadata that a local mirror directory provides).

| Field | Required | Description |
|-------|----------|-------------|
| `url` | yes | a local `spack bootstrap mirror` directory, or a remote `https`/`s3`/`oci` url |

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
| `url`            | yes¹ | location of the source mirror |
| `fetch` / `push` | no¹ | separate read/write [connections](#connections-and-authentication), used instead of a single `url` |
| `source`         | no  | the mirror holds package sources (default `true`) |
| `binary`         | no  | the mirror also holds binary packages (default `false`) |
| `signed`         | no  | whether Spack signs/verifies binaries with GPG (passed through to Spack) |
| `autopush`       | no  | Spack pushes to the mirror as soon as a package is installed (passed through to Spack) |

¹ Give either a top-level `url` *or* explicit `fetch`/`push` connections — see [Connections and authentication](#connections-and-authentication).

Source mirrors need no keys: Spack verifies every downloaded source against the checksum in its package recipe, whether it comes from the upstream url or a mirror.

Populate a source mirror on an internet-connected system with Spack:

```bash
spack mirror create --directory /path/to/mirror --all
```

## Connections and authentication

Both the [build cache](#build-cache) and [source mirrors](#source-mirrors) describe *where* and *how* Spack reaches a mirror with the same connection model, taken directly from Spack's own [`mirrors.yaml`](https://spack.readthedocs.io/en/latest/mirrors.html). Stackinator passes these fields through to Spack unchanged.

The simplest form is a single `url`, used for both reading and writing:

```yaml title="mirrors.yaml"
buildcache:
  url: file:///capstor/scratch/team/uenv-cache
  private_key: $SCRATCH/.keys/spack-push-key.gpg
```

When the read and write endpoints differ, or the mirror needs authentication, replace the top-level `url` with explicit `fetch` and `push` connection blocks. This example is an S3 build cache with credentials supplied through environment variables:

```yaml title="mirrors.yaml"
buildcache:
  private_key: $SCRATCH/.keys/spack-push-key.gpg
  fetch:
    url: s3://my-bucket/buildcache
    endpoint_url: https://s3.example.com
    access_pair:
      id_variable: AWS_ACCESS_KEY_ID
      secret_variable: AWS_SECRET_ACCESS_KEY
  push:
    url: s3://my-bucket/buildcache
    endpoint_url: https://s3.example.com
    access_pair:
      id_variable: AWS_ACCESS_KEY_ID
      secret_variable: AWS_SECRET_ACCESS_KEY
```

A connection — whether given as the top-level shorthand or inside a `fetch`/`push` block — accepts:

| Field | Description |
|-------|-------------|
| `url`                   | location of the mirror (`file://`, `http(s)://`, `s3://` or `oci://`) |
| `endpoint_url`          | custom endpoint URL for S3-compatible storage |
| `profile`               | AWS profile name to use for S3 authentication |
| `access_token_variable` | environment variable holding an access token for OCI registry authentication |
| `access_pair`           | ID + secret credential pair (see below) |
| `view`                  | mirror view (passed through to Spack) |

`access_pair` holds the credential pair:

| Field | Required | Description |
|-------|----------|-------------|
| `secret_variable` | yes | environment variable holding the secret key |
| `id_variable`     | one of | environment variable holding the access key ID |
| `id`              | one of | the access key ID as a literal string (prefer `id_variable`) |

!!! warning "Keep secrets out of the file"
    Reference credentials through environment variables (`*_variable`) rather than writing them into `mirrors.yaml`. The secret itself is never a required field — only the *name* of the variable that holds it.

See Spack's [mirror documentation](https://spack.readthedocs.io/en/latest/mirrors.html) for the full reference on these fields.

## Source cache

A source cache is a single, **writable** local directory that Spack fills as it downloads sources.
On internet-connected systems Spack checks the cache first; on a miss it downloads the source and stores it, so later builds reuse it and download times shrink over time.

Unlike a source mirror it is written to automatically, and is created on demand.

```yaml title="mirrors.yaml"
sourcecache:
  path: /capstor/scratch/bobsmith/spack-sources
```

| Field | Required | Description |
|-------|----------|-------------|
| `path` | yes | absolute path to a local directory (environment variables are expanded) |

## Concretizer cache

The concretizer cache is a single, **writable** local directory in which Spack persists its **concretization results** — the output of concretizing a set of specs, so it does not have to be recomputed.
Concretization can be a large fraction of build time, so pointing this at a persistent location is worthwhile when build directories are ephemeral (e.g. created in `/dev/shm` and deleted after each build).

```yaml title="mirrors.yaml"
concretizer:
  path: /capstor/scratch/bobsmith/spack-concretizer
```

| Field | Required | Description |
|-------|----------|-------------|
| `path` | yes | absolute path to a local directory (environment variables are expanded) |

This emits a `concretizer.yaml` that sets `concretizer:concretization_cache:{enable: true, url}`.
The cache is keyed by the hash of the solver inputs, so it can be reused safely across builds — stale entries simply miss.

!!! info "concretizer cache is not a silver bullet"
    The cache stores only the *result of the solve* for a given set of inputs.
    Before it can be consulted, Spack still has to rebuild the full concretization problem on every run, loading the package recipes and enumerating the reusable packages, and that setup work is often the larger part of concretization.
    So a cache hit skips the solver but not the setup: concretization gets faster, not free.

    The win is therefore largest for repeated builds of the same stack against a stable build cache (the previous solve is replayed), and smallest when the bulk of concretization time is in setup.

!!! note "Requires Spack ≥ 1.1"
    The `concretizer:concretization_cache` config key was introduced in Spack 1.1, and Spack 1.0 rejects it.
    Stackinator infers the Spack version from the `spack.commit` in `config.yaml` (defaulting to a supported version when the commit is a branch or arbitrary SHA that cannot be pinned).
    When it detects Spack 1.0 it skips the concretizer cache with a warning rather than producing a config that would fail the build.

## Keys

The build cache's `private_key` and `public_key` fields accept either:

* a **path** — absolute, or relative to the directory containing `mirrors.yaml`; or
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

!!! warning "Don't use `$HOME`"
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
