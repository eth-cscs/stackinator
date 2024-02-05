# Copyright 2013-2023 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os
import platform

import spack.compilers
from spack.package import *

_versions = {
    "1.3.2": {
        "Linux-aarch64": "f7b97a10cc8dde17e804f79235ab1aa98f83e0c7c178e58d6ca3e9170f89c6da",
        "Linux-x86_64": "deea749476de0f545b31fcd0912f133d7ba60b84f673e47d8b4b15d5a117254c",
    },
    "1.2.12": {
        "Linux-x86_64": "c94d29c09ed650c4e98a236df7ced77f027bdf987919a91a1a1382f704a85bb9"
    },
    "1.2.11": {
        "Linux-x86_64": "e1af09e39d70e28381de806548c6cb29c23abf891a078f46eb71c301a3f0994c"
    },
    "1.2.9": {
        "Linux-x86_64": "ceec6f99bea9df3f7f657a7df499445e62976064dda3f3e437d61e895ec31601"
    },
    "1.2.5": {
        "Linux-x86_64": "d7269ed8f4deab816e3d4006090ec68b25ccc585200d16728ed9a914baf4d9bf"
    },
    "1.2.4": {
        "Linux-x86_64": "a253939585bad2bb9061b98be6e517f18bda0602ecfd38f75c734a01d12003f2"
    },
    "1.2.0": {
        "Linux-x86_64": "6f5c71aa4dd2f591b899ea693cae7a5319d859f69d8c46b7ee244fed8c094d10"
    },
}


class CrayPals(Package):
    """Install cray-pals"""

    """Intended to override the main cray-pals"""

    homepage = "https://www.hpe.com/us/en/compute/hpc/hpc-software.html"
    url = "https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-pals-1.2.12.tar.gz"
    maintainers = ["simonpintarelli"]

    for ver, packages in _versions.items():
        key = "{0}-{1}".format(platform.system(), platform.machine())
        sha = packages.get(key)
        if sha:
            version(
                ver,
                sha256=sha,
                url=f"https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-pals-{ver}.{platform.machine()}.tar.gz",
            )

    # Fix up binaries with patchelf.
    depends_on("patchelf", type="build")

    def get_rpaths(self):
        # Those rpaths are already set in the build environment, so
        # let's just retrieve them.
        pkgs = os.getenv("SPACK_RPATH_DIRS", "").split(":")
        compilers = os.getenv("SPACK_COMPILER_IMPLICIT_RPATHS", "").split(":")
        return ":".join([p for p in pkgs + compilers if p])

    def should_patch(self, file):
        # Returns true if non-symlink ELF file.
        if os.path.islink(file):
            return False
        try:
            with open(file, "rb") as f:
                return f.read(4) == b"\x7fELF"
        except OSError:
            return False

    def install(self, spec, prefix):
        install_tree(".", prefix)

    @run_after("install")
    def fixup_binaries(self):
        patchelf = which("patchelf")
        rpath = self.get_rpaths()
        for root, _, files in os.walk(self.prefix):
            for name in files:
                f = os.path.join(root, name)
                if not self.should_patch(f):
                    continue
                patchelf("--force-rpath", "--set-rpath", rpath, f, fail_on_error=False)
