#!/usr/bin/python3

import argparse
import json
import subprocess
import pathlib
import yaml


def compiler_extra_attributes(name, prefix):
    """Find paths to compiler"""
    if name == "gcc":
        cc = "gcc"
        cxx = "g++"
        f90 = "gfortran"
    elif name == "llvm":
        cc = "clang"
        cxx = "clang++"
        f90 = None
    elif name == "nvhpc":
        cc = "nvc"
        cxx = "nvc++"
        f90 = "nvfortran"
    else:
        # this is not a compiler
        return {}

    def find(comp):
        p = subprocess.run(
            ["find", prefix, "-name", f"{comp}", "-path", "*/bin/*"],
            shell=False,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return p.stdout.strip().decode("utf-8")

    extra_attributes = {"extra_attributes": {"compilers": {"c": find(cc), "cxx": find(cxx)}}}
    if f90 is not None:
        extra_attributes["extra_attributes"]["compilers"]["fortran"] = find(f90)

    return extra_attributes


def gen_packages_impl(lock_file, env_path):
    spack_lock = json.load(open(lock_file, "r"))

    packages = {"packages": {}}

    for dd in spack_lock["roots"]:
        hash = dd["hash"]
        # call subprocess to find install dir
        spack_find_prefix = subprocess.run(
            ["spack", "--color=never", "-e", env_path, "find", "--format={prefix}", f"/{hash}"],
            shell=False,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        spack_find_spec = subprocess.run(
            ["spack", "--color=never", "-e", env_path, "find", "--format={name}|{version}|{variants}", f"/{hash}"],
            shell=False,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        name, version, variants = spack_find_spec.stdout.strip().decode("utf-8").split("|")
        prefix = spack_find_prefix.stdout.strip().decode("utf-8")

        packages["packages"][name] = {
            "buildable": False,
            "externals": [
                {
                    "spec": f"{name}@{version} {variants}",
                    "prefix": prefix,
                }
            ],
        }
        # add `extra_attributes` for compilers
        if name in ["gcc", "nvhpc", "llvm"]:
            extra_attributes = compiler_extra_attributes(name, prefix)
            packages["packages"][name]["externals"][0].update(extra_attributes)

        return packages


if __name__ == "__main__":
    # parse CLI arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock-file", help="spack.lock", type=str)
    parser.add_argument("--env-path", help="path to spack env", type=str)
    parser.add_argument("--view", help="path to spack view", type=str)

    args = parser.parse_args()

    packages = gen_packages_impl(args.lock_file, args.env_path)

    dst = pathlib.Path(args.view) / "packages.yaml"
    with open(dst, "w") as f:
        yaml.dump(packages, f)
