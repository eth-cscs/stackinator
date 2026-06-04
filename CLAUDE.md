# Stackinator

Stackinator is a Python CLI tool that generates build configurations for scientific software stacks on HPE Cray EX (Alps) systems. It acts like `cmake`/`configure`: given a **recipe** and a **cluster configuration**, it produces a build directory with Makefiles and Spack YAML files. The actual build is then performed by `make`.

## Two-Phase Workflow

```
stack-config -b BUILD -r RECIPE -s SYSTEM [-c CACHE] [-m MOUNT]
    → generates BUILD/ directory with Makefiles + spack.yaml files

cd BUILD
env --ignore-environment PATH=/usr/bin:/bin:`pwd -P`/spack/bin make store.squashfs -j64
    → clones Spack, concretises, builds, creates store.squashfs
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
    Makefile            # Top-level build orchestration
    Makefile.compilers  # Compiler build steps
    Makefile.environments # Environment build + view generation steps
    Makefile.generate-config # Generates upstream spack config for the uenv
    Make.user           # Build path / store / sandbox variable definitions
    repos.yaml          # Generated spack repos.yaml
    stack-debug.sh      # Debug helper script
    compilers.*.spack.yaml  # Per-compiler spack.yaml configs
    environments.spack.yaml # Environment spack.yaml config
  etc/
    Make.inc            # Shared make rules (concretize, depfile, compiler_bin_dirs)
    bwrap-mutable-root.sh  # Bubblewrap sandbox wrapper
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
version: 2                      # must be 2 for Spack 1.0 (Stackinator 6+)
spack:
  repo: https://github.com/spack/spack.git
  commit: releases/v1.0         # branch, tag, or SHA; null = default branch
  packages:
    repo: https://github.com/spack/spack-packages.git
    commit: develop
description: "optional text"
default-view: develop           # optional: view loaded when no view is specified
```

- `version: 1` (the default) targets Spack v0.23 and is only supported by Stackinator v5 (`releases/v5` branch). **Current `main` requires `version: 2`.**
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

Build order: `gcc` is built first (using system compiler), then `nvhpc`/`llvm`/`llvm-amdgpu`/`intel-oneapi-compilers` are built using the gcc toolchain. Stackinator appends opinionated variants (e.g. `gcc@13 +bootstrap`, `nvhpc@25.1 ~mpi~blas~lapack`, `llvm@16 +clang ~gold`).

### `environments.yaml` (required)
```yaml
my-env:
  compiler: [gcc]               # required; list from compilers.yaml keys; first = default
  specs:                        # required; list of spack specs
    - cmake
    - hdf5+mpi
  network:                      # optional; null = no MPI
    mpi: cray-mpich             # full spack spec for MPI (cray-mpich or openmpi)
    specs: ['libfabric@1.22']   # optional; overrides network.yaml defaults
  unify: true                   # concretizer: true | false | when_possible (default true)
  duplicates:
    strategy: minimal           # minimal | full | none (default minimal)
  deprecated: false             # allow deprecated spack versions (default false)
  variants:                     # applied to all packages (packages:all:variants)
    - +cuda
    - cuda_arch=80
  prefer: null                  # packages:all:prefer; auto-set if null
  packages:                     # external packages to discover via `spack external find`
    - perl
    - git
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

Package precedence (recipe.py merges these): recipe `packages.yaml` > `network.yaml` packages > `packages.yaml` (minus gcc). The `gcc` entry from `packages.yaml` is isolated and used only for the gcc compiler build step.

## Build Directory Structure (output)

```
BUILD/
  Makefile              # top-level orchestration
  Make.user             # variables: BUILD_ROOT, STORE, SANDBOX, etc.
  Make.inc              # shared make rules (copied from etc/)
  bwrap-mutable-root.sh # sandbox wrapper (copied from etc/)
  envvars.py            # view/meta generator (copied from etc/)
  spack/                # cloned Spack repository
  spack-packages/       # cloned spack-packages repository
  config/               # global spack configuration scope
    packages.yaml
    mirrors.yaml        # only if --cache provided
    repos.yaml
  compilers/
    Makefile
    gcc/
      spack.yaml
      packages.yaml     # generated by spack external find
    nvhpc/              # if nvhpc in recipe
      spack.yaml
  environments/
    Makefile
    my-env/
      spack.yaml
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
- Merges packages from cluster config, network.yaml, and recipe
- Generates full compiler specs (e.g. `gcc@13 +bootstrap`) from `compilers.yaml`
- Processes environments: resolves MPI specs from `network.yaml` templates, sets default `prefer` constraints, builds view metadata
- Provides `compiler_files` and `environment_files` properties (Jinja-rendered Makefiles and spack.yaml files)

### `Builder` class (`builder.py`)
Writes all files to the build path. Key responsibilities:
- Creates directory structure
- Clones Spack and spack-packages repositories
- Merges and writes the consolidated `alps` spack package repo
- Renders all Jinja templates into build path files
- Writes metadata JSON files

### `schema.py`
JSON schema validation using `jsonschema`. The `validator()` function extends the validator to auto-inject `default` values from schemas into parsed instances, so downstream code can rely on optional fields always being present.

### `etc/envvars.py`
A standalone CLI tool (copied into the build directory) with two subcommands:
- `envvars.py view <root> <build_path> [--compilers] [--prefix_paths]`: reads a Spack-generated `activate.sh`, parses env vars, adds compiler symlinks and prefix paths, writes `env.json` for the view
- `envvars.py uenv <mount> [--modules] [--spack]`: merges view `env.json` files with recipe `env_vars` config, writes the final `meta/env.json`

The `EnvVarSet` class in `envvars.py` is also imported by `recipe.py` for processing `env_vars` at configure time.

## Build Pipeline (Make targets)

The top-level `Makefile` orchestrates in order:
1. `spack-setup` — sanity check, bootstrap concretizer
2. `pre-install` — run `pre-install-hook` if provided
3. `mirror-setup` — configure build cache keys
4. `compilers` — build gcc, then nvhpc/llvm/etc. (parallel within each stage)
5. `environments` — build all user environments (parallel)
6. `generate-config` — generate the upstream spack config files for the installed image
7. `modules-done` — generate TCL module files (if `modules.yaml` present)
8. `env-meta` — run `envvars.py uenv` to produce final `meta/env.json`
9. `post-install` — run `post-install-hook` if provided
10. `store.squashfs` — create the final squashfs image

Key Make.inc rules:
- `%/spack.lock`: concretize a spack environment
- `%/Makefile`: generate a depfile from a lock file (enables parallel package builds)
- `compiler_bin_dirs`: helper to find compiler binaries given install prefixes

The build runs inside a bwrap sandbox (`bwrap-mutable-root.sh`) that:
- Bind-mounts `BUILD/store` → `STORE` (the recipe mount point)
- Bind-mounts `BUILD/tmp` → `/tmp`
- Puts a tmpfs over `$HOME` (isolates user config)

## Build Cache

Optional binary cache configured via YAML file passed to `-c/--cache`:
```yaml
root: /path/to/cache       # directory; env vars expanded
key: /path/to/pgp.key      # optional; omit for read-only cache
```

Cache is stored in a subdirectory named after the mount point (e.g. `cache/user-environment/`) to avoid relocation issues. Packages are pushed per-environment after a successful build. Large binary packages (`cuda`, `nvhpc`, `perl`) are excluded from cache pushes.

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
- **Version 2 is required**: `config.yaml` must have `version: 2` for current `main`. Version 1 recipes require the `releases/v5` branch.
- **gcc is required**: `packages.yaml` in cluster config must define an external `gcc`. It is handled separately from other system packages for the bootstrap build step.
- **MPI validation**: the MPI name in `network.mpi` must match a key in `network.yaml:mpi` templates from the cluster config. Unknown MPI implementations raise an error.
- **View names are globally unique**: view names must be unique across all environments in a recipe.
- **`mirrors.yaml` in recipes is unsupported**: use `--cache` CLI flag instead.
- **`default-view` must exist**: if set in `config.yaml`, the named view must be defined in `environments.yaml` (or be `modules`/`spack`).
- **`prefer` is auto-set**: if `null` in the recipe, Stackinator generates a `prefer` constraint using Spack's `%[when=...]` syntax to pin the default compiler.
- **Spack `uenv_tools` environment**: an internal environment named `uenv_tools` is injected into every build to install `squashfs`. Recipe authors must not use this name.
