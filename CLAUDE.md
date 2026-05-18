# Stackinator

Stackinator is a Python CLI tool that generates build configurations for scientific software stacks on HPE Cray EX (Alps) systems. It acts like `cmake`/`configure`: given a **recipe** and a **cluster configuration**, it produces a build directory with a Makefile and a single `spack.yaml`. The actual build is then performed by `make`.

**Stackinator v7 (this branch) supports only version 3 recipes (Spack 1.2+).** For version 2 recipes use the `releases/v6` branch.

## Two-Phase Workflow

```
stack-config -b BUILD -r RECIPE -s SYSTEM [-c CACHE] [-m MOUNT]
    → generates BUILD/ directory with Makefile + spack.yaml

cd BUILD
env --ignore-environment PATH=/usr/bin:/bin:`pwd -P`/spack/bin make store.squashfs -j64
    → clones Spack, concretises all spec groups, builds, creates store.squashfs
```

The `store.squashfs` SquashFS image is the final artifact, intended to be mounted at the recipe's `store` path (default `/user-environment`) as a uenv image.

## Repository Layout

```
stackinator/           # Python package
  main.py              # CLI entry point (stack-config)
  recipe.py            # Recipe class: parses and validates all recipe YAML
  builder.py           # Builder class: writes all files to the build path
  cache.py             # Build cache configuration helpers
  spack_util.py        # Tiny helper: checks if a path is a spack package repo
  schema.py            # JSON schema validators with default-injection
  schema/              # JSON schemas for each YAML file type
    config.json
    compilers.json
    environments.json
    cache.json
    modules.json
  templates/           # Jinja2 templates for all generated files
    Makefile            # Top-level build orchestration (single concretize + install)
    Makefile.generate-config # Generates upstream spack config for the uenv
    Make.user           # Build path / store / sandbox variable definitions
    repos.yaml          # Generated spack repos.yaml
    spack.yaml          # Unified spack.yaml with spec groups for all compilers + envs
    stack-debug.sh      # Debug helper script
  etc/
    Make.inc            # Shared make rules
    bwrap-mutable-root.sh  # Bubblewrap sandbox wrapper
    compiler-config.py  # Spack Python script: generates packages.yaml with compiler externals
    envvars.py          # CLI tool: generates env.json for views and uenv metadata
docs/                  # MkDocs documentation source
unittests/             # pytest test suite
  test_schema.py        # Schema validation tests (primary test coverage)
  recipes/              # Example recipes used by tests
  yaml/                 # Example YAML snippets for testing
```

## Recipe Format (input)

A recipe is a directory containing YAML files:

### `config.yaml` (required)
```yaml
name: prgenv-gnu
store: /user-environment        # mount point; default /user-environment
version: 3                      # must be 3; v1/v2 require Stackinator v6
spack:
  repo: https://github.com/spack/spack.git
  commit: releases/v1.2         # branch, tag, or SHA; null = default branch
  packages:
    repo: https://github.com/spack/spack-packages.git
    commit: develop
description: "optional text"
default-view: develop           # optional: view loaded when no view is specified
```

- `store` can be overridden at configure time with `-m/--mount`.

### `compilers.yaml` (required)
```yaml
gcc:
  version: "13"          # required; must be quoted string
nvhpc:                   # optional
  version: "25.1"
llvm:                    # optional
  version: "16"
llvm-amdgpu:             # optional
  version: "6.0"
intel-oneapi-compilers:  # optional
  version: "2024.1"
```

Build order: `gcc` is built first (using system compiler), then `nvhpc`/`llvm`/`llvm-amdgpu`/`intel-oneapi-compilers` are built using the gcc toolchain. Stackinator appends opinionated variants (e.g. `gcc@13 +bootstrap`, `nvhpc@25.1 ~mpi~blas~lapack`, `llvm@16 +clang ~gold`). Each compiler becomes a separate spec group in the unified `spack.yaml`.

### `environments.yaml` (required)
```yaml
my-env:
  compiler: [gcc]               # required; list from compilers.yaml keys; first = default
  specs:                        # required; list of spack specs
    - cmake
    - hdf5+mpi
  network:                      # optional; null = no MPI
    mpi: cray-mpich             # MPI implementation name (must match network.yaml key)
    specs: ['libfabric@1.22']   # optional; overrides network.yaml defaults
  unify: true                   # concretizer: true | false | when_possible (default true)
  duplicates:
    strategy: minimal           # minimal | full | none (default minimal)
  deprecated: false             # allow deprecated spack versions (default false)
  variants:                     # applied to all packages (packages:all:variants)
    - +cuda
    - cuda_arch=80
  prefer: null                  # packages:all:prefer; auto-set if null
  views:                        # optional filesystem views
    default: null               # view name → view config (null = defaults)
    no-python:
      exclude: [python]
      uenv:
        add_compilers: true     # default true; adds compiler symlinks to view/bin
        prefix_paths:
          LD_LIBRARY_PATH: [lib, lib64]
        env_vars:
          set:
            - MYVAR: "value"
            - MYVAR2: null      # unsets the variable
          prepend_path:
            - PATH: "/some/path"
          append_path:
            - PKG_CONFIG_PATH: "/usr/lib/pkgconfig"
```

**Key constraints:**
- Do not include MPI or compilers in `specs`; they are handled by `network.mpi` and `compiler`.
- Spec matrices are not supported.
- Only one MPI per environment; create separate environments for multiple MPIs.
- The `prefer` field is auto-generated if `null`: it nudges Spack to use the first compiler for all packages.
- The `packages` field (list of package names for `spack external find`) is accepted by the schema but **ignored in v3 recipes** — a warning is emitted. Add external packages to `packages.yaml` instead.

#### Environment variable special syntax
- `${@VAR@}` — deferred expansion: expands `VAR` at uenv load time (e.g. `${@HOME@}`)
- `$@key@` — substitution at configure time: `mount`, `view_name`, `view_path`

#### Supported prefix-path variables (hardcoded in `etc/envvars.py`)
`ACLOCAL_PATH`, `CMAKE_PREFIX_PATH`, `CPATH`, `LD_LIBRARY_PATH`, `LIBRARY_PATH`, `MANPATH`, `MODULEPATH`, `PATH`, `PKG_CONFIG_PATH`, `PYTHONPATH`

### `modules.yaml` (optional)
Presence of this file enables module generation. Follows Spack's module config format with two differences:
- `modules:default:arch_folder` must be `false` (Stackinator doesn't support `true`)
- `modules:default:roots:tcl` is ignored and overwritten by Stackinator

### `packages.yaml` (optional)
Standard Spack `packages.yaml` with recipe-specific external package overrides.

### `repo/` (optional)
Custom Spack package definitions. Must contain a `packages/` subdirectory.
Merged into a single `alps` namespace repo alongside system and site packages.
Precedence: recipe repo > site repos (from cluster config `repos.yaml`) > Spack builtin.

### `post-install` / `pre-install` (optional)
Shell scripts (any language) run inside the bwrap sandbox:
- `pre-install`: after Spack is set up, before first compiler build
- `post-install`: after all packages are built, before squashfs generation

Both are Jinja-templated with variables: `env.mount`, `env.config`, `env.build`, `env.spack`.

### `extra/` (optional)
Arbitrary files copied to `meta/extra/` in the final image (used for CI metadata).

## Cluster Configuration (input)

A directory (passed via `-s/--system`) containing:

```
cluster-config/
  packages.yaml   # Spack external packages; must include gcc
  network.yaml    # MPI defaults and network library package configs
  repos.yaml      # optional; list of relative paths to site-wide spack repos
```

`network.yaml` structure:
```yaml
mpi:
  cray-mpich:
    specs: [libfabric@1.22]   # default specs injected when cray-mpich is chosen
  openmpi:
    specs: [libfabric@2.2.0]
packages:                     # standard spack packages.yaml content
  libfabric: ...
  cray-mpich: ...
```

Package precedence (`recipe.py` merges these): recipe `packages.yaml` > `network.yaml` packages > cluster `packages.yaml`. All packages (including gcc externals) go into a single global `packages.yaml` that is included by the unified `spack.yaml`.

## Build Directory Structure (output)

```
BUILD/
  Makefile              # top-level orchestration (single concretize + install)
  Make.user             # variables: BUILD_ROOT, STORE, SANDBOX, etc.
  Make.inc              # shared make rules (copied from etc/)
  bwrap-mutable-root.sh # sandbox wrapper (copied from etc/)
  envvars.py            # view/meta generator (copied from etc/)
  compiler-config.py    # compiler external generator (copied from etc/)
  spack.yaml            # unified spack.yaml with all spec groups
  packages.yaml         # merged system + network + recipe packages
  config.yaml           # spack install tree location
  spack/                # cloned Spack repository
  spack-packages/       # cloned spack-packages repository
  config/               # SPACK_SYSTEM_CONFIG_PATH scope
    repos.yaml
    mirrors.yaml        # only if --cache provided
  generate-config/      # generates the upstream spack config for the final image
    Makefile
  modules/              # only if modules.yaml in recipe
    modules.yaml
  store/                # installation root (bind-mounted to recipe.store during build)
    meta/
      configure.json    # build metadata
      env.json.in       # view metadata template
      recipe/           # copy of the recipe
    repos/spack_repo/alps/   # consolidated custom package repo
    repos/spack_repo/builtin/ # copy of spack builtin repo
    env/                # filesystem views (created during build)
      view-name/
        activate.sh
        env.json
        bin/ lib/ ...
  store.squashfs        # final compressed image
  stack-debug.sh        # debug helper: opens shell in build environment
```

## Python Architecture

### `Recipe` class (`recipe.py`)
Parses and validates all recipe inputs in `__init__`. Key responsibilities:
- Validates each YAML file against its JSON schema (with default injection)
- Merges packages from cluster config, network.yaml, and recipe into a single dict
- Generates full compiler specs (e.g. `gcc@13 +bootstrap`) from `compilers.yaml`
- Processes environments: resolves MPI specs from `network.yaml` templates, sets default `prefer` constraints, builds view metadata
- Provides `spack_yaml` property (Jinja-rendered unified spack.yaml with spec groups)
- Provides `compiler_names` property (list of compiler package names for `compiler-config.py`)

### `Builder` class (`builder.py`)
Writes all files to the build path. Key responsibilities:
- Creates directory structure
- Clones Spack and spack-packages repositories
- Merges and writes the consolidated `alps` spack package repo
- Writes the unified `spack.yaml`, `packages.yaml`, and `config.yaml` to `BUILD_ROOT`
- Renders Makefile, Make.user, generate-config/Makefile from Jinja2 templates
- Copies `Make.inc`, `bwrap-mutable-root.sh`, `envvars.py`, `compiler-config.py` from `etc/`
- Writes metadata JSON files

### `schema.py`
JSON schema validation using `jsonschema`. The `validator()` function extends the validator to auto-inject `default` values from schemas into parsed instances, so downstream code can rely on optional fields always being present. `check_config_version` enforces version 3 and gives a clear error for v1/v2 recipes pointing to the `releases/v6` branch.

### `etc/compiler-config.py`
Replaces `spack compiler find`. Run as `spack -e BUILD_ROOT python compiler-config.py OUTPUT_YAML COMPILER...`. Uses `spack.store.STORE.db.query()` to find installed compiler packages, walks the install prefix to locate binaries, and writes (or merges into) a `packages.yaml` with `extra_attributes.compilers` entries. This is how compilers become available to downstream Spack users without a `compilers.yaml`.

### `etc/envvars.py`
A standalone CLI tool (copied into the build directory) with two subcommands:
- `envvars.py view <root> <build_path> [--compilers=FILE] [--prefix_paths=STR]`: reads a Spack-generated `activate.sh`, parses env vars, adds compiler symlinks and prefix paths, writes `env.json` for the view
- `envvars.py uenv <mount> [--modules] [--spack=...]`: merges view `env.json` files with recipe `env_vars` config, writes the final `meta/env.json`

The `EnvVarSet` class in `envvars.py` is also imported by `recipe.py` for processing `env_vars` at configure time.

## Build Pipeline (Make targets)

The top-level `Makefile` orchestrates in order:
1. `spack-setup` — sanity check, bootstrap concretizer
2. `pre-install` — run `pre-install-hook` if provided (optional)
3. `mirror-setup` — configure build cache keys
4. `concretize` — `spack -e BUILD_ROOT concretize` (all spec groups in one pass)
5. `install` — `spack -e BUILD_ROOT install` (all groups in dependency order)
6. `compiler-config.yaml` — run `compiler-config.py` to generate packages.yaml with compiler externals
7. `views/NAME` — per-view: generate `activate.sh` via `spack env activate`, then run `envvars.py view`
8. `views` — aggregate target for all views
9. `generate-config` — `make -C generate-config` (writes store/config/{upstreams,packages,repos}.yaml)
10. `modules-done` — `spack module tcl refresh` (if `modules.yaml` present)
11. `env-meta` — run `envvars.py uenv` to produce final `meta/env.json`
12. `post-install` — run `post-install-hook` if provided (optional)
13. `cache-push` — push to build cache (if cache with key configured)
14. `store.squashfs` — create the final squashfs image using the `squashfs` package installed in the `uenv_tools` spec group

The `uenv_tools` spec group (hardcoded in the `spack.yaml` template) installs `squashfs` as an implicit dependency of gcc, providing the `mksquashfs` binary for image creation.

All spack commands use `$(SANDBOX) $(SPACK) -e $(BUILD_ROOT)` — there is a single spack environment at the build root.

The build runs inside a bwrap sandbox (`bwrap-mutable-root.sh`) that:
- Bind-mounts `BUILD/store` → `STORE` (the recipe mount point)
- Bind-mounts `BUILD/tmp` → `/tmp`
- Puts a tmpfs over `$HOME` (isolates user config)

## Spec Groups in spack.yaml

The unified `spack.yaml` uses Spack 1.2 spec groups to express the build order and per-group concretizer settings. Structure:

- **gcc group**: `explicit: false`, override sets static-library variants for gcc's dependencies (mpc, gmp, mpfr, zstd, zlib)
- **nvhpc/llvm/llvm-amdgpu/intel-oneapi-compilers groups**: `explicit: false`, `needs: [gcc]`, `reuse: false`
- **uenv_tools group**: `explicit: false`, `needs: [gcc]`, installs `squashfs`
- **user environment groups**: `needs: [compiler list]`, override sets `concretizer.unify`, `concretizer.duplicates.strategy`, `packages.all.prefer`, `packages.all.variants`, and `packages.mpi.require` per-environment

Per-group `override:` blocks are pushed as the highest-priority config scope during that group's concretization, so `unify` and `duplicates.strategy` settings are truly per-group.

## Build Cache

Optional binary cache configured via YAML file passed to `-c/--cache`:
```yaml
root: /path/to/cache       # directory; env vars expanded
key: /path/to/pgp.key      # optional; omit for read-only cache
```

Cache is stored in a subdirectory named after the mount point (e.g. `cache/user-environment/`) to avoid relocation issues. Packages are pushed in a single `cache-push` step. Large binary packages (`cuda`, `nvhpc`, `perl`) are excluded from cache pushes.

## Testing

```bash
uv run pytest            # run tests
./lint                   # ruff format + ruff check --fix
```

Tests live in `unittests/test_schema.py` and cover schema validation and default injection. Test recipes are in `unittests/recipes/`, example YAML in `unittests/yaml/`.

The test coverage is limited — the schema validators and their default-injection are well tested, but `Recipe`, `Builder`, and `envvars.py` have minimal test coverage.

## Code Style

- Python 3.12+
- Linting: `ruff` (line length 120, E + F rules, E203 ignored)
- Format: `ruff format`
- Run both via `./lint`

## Key Invariants and Pitfalls

- **Build path restrictions**: cannot be in `/tmp`, `$HOME`, or root `/`. The bwrap sandbox rebinds these.
- **Version 3 is required**: `config.yaml` must have `version: 3`. Versions 1 and 2 raise a clear error pointing to the `releases/v6` branch.
- **gcc is required**: cluster `packages.yaml` must define an external `gcc`. It is merged into the global packages.yaml and used by the gcc spec group's override.
- **MPI validation**: the MPI name in `network.mpi` must match a key in `network.yaml:mpi` templates from the cluster config. Unknown MPI implementations raise an error.
- **View names are globally unique**: view names must be unique across all environments in a recipe.
- **`mirrors.yaml` in recipes is unsupported**: use `--cache` CLI flag instead.
- **`default-view` must exist**: if set in `config.yaml`, the named view must be defined in `environments.yaml` (or be `modules`/`spack`).
- **`prefer` is auto-set**: if `null` in the recipe, Stackinator generates a `prefer` constraint using Spack's `%[when=...]` syntax to pin the default compiler.
- **`uenv_tools` is reserved**: a spec group named `uenv_tools` is hardcoded in the spack.yaml template to install `squashfs`. Recipe authors must not use this environment name.
- **`packages` field in environments.yaml is ignored**: in v3 recipes, the `packages` list (formerly used to drive `spack external find`) is silently ignored with a warning. Add external packages to `packages.yaml` instead.
- **compiler-config.py must run inside spack python**: it imports `spack.store` and must be invoked as `spack -e BUILD_ROOT python compiler-config.py` to access the correct spack DB.
