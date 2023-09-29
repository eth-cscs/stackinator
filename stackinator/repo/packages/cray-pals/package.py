# Copyright 2013-2023 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os

import spack.compilers
from spack.package import *


class CrayPals(Package):
    """Install cray-pals"""

    """Intended to override the main cray-pals"""

    homepage = "https://www.hpe.com/us/en/compute/hpc/hpc-software.html"
    url = "https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-pals-1.2.12.tar.gz"
    maintainers = ["simonpintarelli"]

    version(
        "1.2.12",
        sha256="0bcade87c7e466f5ba6c5d096a084764ebae5b5b2ecdb90f3f01b00cd9545337",
    )
    version(
        "1.2.11",
        sha256="52c11e864a603fa07a37ce508fa8b9861b30d15e83c16e33612df5ee85ca6135",
    )
    version(
        "1.2.9",
        sha256="e563a6a8962c15deebc466454fe6860576e33c52fd2cbdcd125e2164613c29fa",
    )
    version(
        "1.2.5",
        sha256="81bfbd433f3276694da3565c1be03dd47887e344626bfe7f43d0de1d73fcb567",
    )
    version(
        "1.2.4",
        sha256="ec5b61a9dcabb6acf2edba305570f0ed9beed80ccec2d3a3f0afd853f080645b",
    )
    version(
        "1.2.0",
        sha256="eaefdd5d7e8031a617ecb1277d4fc79cc34b150a1d109358db0118f66de45a14",
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
