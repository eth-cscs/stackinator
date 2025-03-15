#!/usr/bin/python3

import argparse
import json
import subprocess
import pathlib
import yaml


def gen_packages_impl(lock_file, env_path):
    spack_lock = json.load(open(lock_file, "r"))

    packages = {"packages": {}}

    for dd in spack_lock["roots"]:
        hash = dd["hash"]
        # call subprocess to find install dir
        spack_find_prefix = subprocess.run(
            ["spack", "--color=never", "-e", env_path, "find", "--format={prefix}", f"/{hash}"],
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        spack_find_spec = subprocess.run(
            ["spack", "--color=never", "-e", env_path, "find", "--format={name} {variants}", f"/{hash}"],
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        prefix = spack_find_prefix.stdout.strip().decode("utf-8")
        spec = spack_find_spec.stdout.strip().decode("utf-8")

        packages[spec] = {"externals": [{"spec": spec, "prefix": prefix}]}

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
