#!/usr/bin/env python3
"""
Generate or update a packages.yaml file with compiler externals derived from
installed Spack packages. Intended to be run as:

    spack -e BUILD_ROOT python compiler-config.py OUTPUT_YAML COMPILER [COMPILER ...]

If OUTPUT_YAML already exists (e.g. the build packages.yaml), the compiler
entries are merged in rather than replacing existing content.
"""

import argparse
import os
import sys

import yaml


_COMPILER_BINS = {
    "gcc": [("gcc", "c"), ("g++", "cxx"), ("gfortran", "fortran")],
    "llvm": [("clang", "c"), ("clang++", "cxx"), ("flang-new", "fortran")],
    "llvm-amdgpu": [("clang", "c"), ("clang++", "cxx"), ("flang-new", "fortran")],
    "nvhpc": [("nvc", "c"), ("nvc++", "cxx"), ("nvfortran", "fortran")],
    "intel-oneapi-compilers": [("icx", "c"), ("icpx", "cxx"), ("ifx", "fortran")],
}


def find_compiler_bins(prefix, compiler_name):
    """
    Return a dict mapping language keys (c, cxx, fortran) to absolute binary
    paths found under prefix, or None if nothing was found.
    """
    candidates = _COMPILER_BINS.get(compiler_name, [])
    result = {}
    for root, _dirs, files in os.walk(prefix):
        for exe, lang in candidates:
            if lang not in result and exe in files:
                full = os.path.join(root, exe)
                if os.access(full, os.X_OK):
                    result[lang] = full
        if len(result) == len(candidates):
            break
    return result or None


def build_compiler_packages(compiler_names):
    """
    Query the active Spack DB for each compiler name and return a dict
    suitable for merging into packages.yaml.
    """
    import spack.store

    packages = {}
    for name in compiler_names:
        specs = list(spack.store.STORE.db.query(name, explicit=False))
        if not specs:
            print(f"  compiler-config: no installed specs found for '{name}'", file=sys.stderr)
            continue

        externals = []
        for spec in specs:
            # Skip externals such as the system gcc. It is registered in the
            # cluster packages.yaml and gets pulled into the DB as a bootstrap
            # dependency, but only compilers actually built into this environment
            # should be surfaced here. The system compiler is included separately,
            # and only when selected, via --system-packages.
            if spec.external:
                continue
            prefix = str(spec.prefix)
            bins = find_compiler_bins(prefix, name)
            if not bins:
                print(f"  compiler-config: no binaries found for {name} at {prefix}", file=sys.stderr)
                continue
            externals.append(
                {
                    "spec": f"{spec.name}@{spec.version}",
                    "prefix": prefix,
                    "extra_attributes": {"compilers": bins},
                }
            )
            print(f"  compiler-config: found {name}@{spec.version} at {prefix}", file=sys.stderr)

        if externals:
            packages[name] = {"externals": externals, "buildable": False}

    return packages


def load_system_compiler_externals(system_packages_path):
    """
    Read a packages.yaml and return entries that carry extra_attributes.compilers.
    Used to surface system (external) compilers such as system gcc into the output.
    """
    with open(system_packages_path) as fid:
        data = yaml.safe_load(fid) or {}

    packages = {}
    for pkg_name, pkg_data in data.get("packages", {}).items():
        if not isinstance(pkg_data, dict):
            continue
        compiler_externals = [
            e
            for e in pkg_data.get("externals", [])
            if isinstance(e, dict) and "extra_attributes" in e and "compilers" in e["extra_attributes"]
        ]
        if compiler_externals:
            packages[pkg_name] = {"externals": compiler_externals, "buildable": False}
            print(f"  compiler-config: found system compiler '{pkg_name}' in {system_packages_path}", file=sys.stderr)

    return packages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="Path to packages.yaml to create or update")
    parser.add_argument("compilers", nargs="*", help="Compiler package names to query")
    parser.add_argument(
        "--system-packages",
        help="Path to a packages.yaml to read system compiler externals from",
        default=None,
    )
    args = parser.parse_args()

    # Load existing content if the file already exists (merge mode).
    existing = {}
    if os.path.isfile(args.output):
        with open(args.output) as fid:
            existing = yaml.safe_load(fid) or {}

    compiler_packages = build_compiler_packages(args.compilers)

    # Pull in any system compiler externals (e.g. system gcc) that carry
    # extra_attributes.compilers but are not in the spack store.
    if args.system_packages and os.path.isfile(args.system_packages):
        system_externals = load_system_compiler_externals(args.system_packages)
        for pkg_name, pkg_data in system_externals.items():
            if pkg_name not in compiler_packages:
                compiler_packages[pkg_name] = pkg_data

    # Merge: compiler entries overwrite any existing entry for the same package name.
    merged = existing.copy()
    merged.setdefault("packages", {}).update(compiler_packages)

    with open(args.output, "w") as fid:
        yaml.dump(merged, fid, default_flow_style=False)

    print(f"  compiler-config: wrote {args.output}", file=sys.stderr)


main()
