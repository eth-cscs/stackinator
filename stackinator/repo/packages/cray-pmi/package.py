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
        "6.1.11",
        sha256="de6c6b3e31ff884c0192c7bac7b999167710850cae8a663f5c20c4af30f40c3d",
    )
    version(
        "6.1.10",
        sha256="548dc1ed44b86ca85f52da1bb6af9abbfb71a6a434170f86bbf9219cb2f0a913",
    )
    version(
        "6.1.9",
        sha256="9839585ca211b665b66a34ee9d81629a7529bebef45b664d55e9b602255ca97e",
    )
    version(
        "6.1.8",
        sha256="b8e94335ca3857dc4895e416b91eaeaee5bfbbe928b5dcfc15300239401a8b7b",
    )
    version(
        "6.1.7",
        sha256="7cf52023ef54d82e1836712b12bf6f6a179ae562e35b0f710ca4c7086f4e35e5",
    )
    version(
        "6.0.17",
        sha256="4fc1f8cc32a98f7f3d339915564347b75db8c373647f748bde01daaf0ac4bf70",
    )

    # Fix up binaries with patchelf.
    depends_on("patchelf", type="build")
    depends_on("cray-pals@1.2.12", type="link", when="@6.1.11")
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
