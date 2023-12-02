# Copyright 2013-2023 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os

import spack.compilers
from spack.package import *


class CrayPmi(Package):
    """Install cray-pmi"""

    """Intended to override the main cray-pmi"""

    homepage = "https://www.hpe.com/us/en/compute/hpc/hpc-software.html"
    url = "https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-pmi-6.1.11.tar.gz"
    maintainers = ["bcumming"]

    version(
        "6.1.13",
        sha256="217ac554cf84a4c7f08cd149c6a18428e1e3533d73e350fa291b6800895b632e",
    )
    version(
        "6.1.12",
        sha256="0f1caa93c881e1a5a4b5a65d1cb3a04d9c549ffdb9524b53a6e7ca9317dd90ee",
    )
    version(
        "6.1.11",
        sha256="5ebcece6a610da02cd41a9a386fd7463ee909bd55e3370d6d372603f90be9afe",
    )
    version(
        "6.1.10",
        sha256="f4fbe75c201a171dcfe6ada773a4bf0c606767a0b7a8a76fd19d10852abe1290",
    )
    version(
        "6.1.9",
        sha256="8fd4194c6c5167f8b81b1cf9b76341669e40d647d0caecef287be6f0f5d95290",
    )
    version(
        "6.1.8",
        sha256="6c7e5d3038e26b9d0e82428b25b570d00401a6fc9f2fd3c008f15a253a8e2305",
    )
    version(
        "6.1.7",
        sha256="574b21bd6f8970521c2bc4f096aced896fec8b749f854272cc7bbb7130ae92d8",
    )

    # Fix up binaries with patchelf.
    depends_on("patchelf", type="build")

    depends_on("cray-pals@1.3.2", type="link", when="@6.1.13:")
    depends_on("cray-pals@1.2.12", type="link", when="@6.1.11:6.1.12")
    depends_on("cray-pals@1.2.11", type="link", when="@6.1.10")
    depends_on("cray-pals@1.2.9", type="link", when="@6.1.9")
    depends_on("cray-pals@1.2.5", type="link", when="@6.1.8")
    depends_on("cray-pals@1.2.4", type="link", when="@6.1.7")
    depends_on("cray-pals@1.2.0", type="link", when="@6.0.17")

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

    @property
    def libs(self):
        return find_libraries(["libmpi", "libpmi2"], root=self.prefix, shared=True)

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
