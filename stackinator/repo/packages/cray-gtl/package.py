# Copyright 2013-2023 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os

import spack.compilers
from spack.package import *


class CrayGtl(Package):
    """Install cray-gtl"""

    homepage = "https://www.hpe.com/us/en/compute/hpc/hpc-software.html"
    url = "https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-gtl-8.1.26.tar.gz"
    maintainers = ["bcumming"]

    version(
        "8.1.26",
        sha256="319e4e2ac0f06c1272ac6ba756924e2a5b239857b3a3b58e7a9a4672aa63c138",
    )
    version(
        "8.1.25",
        sha256="527c63823ea3a15ca989ded43f8b085e40baad38b9276d6893b8dce3fdf91254",
    )
    version(
        "8.1.24",
        sha256="980cbc3538501e5422528e12cb7b99d3e5b21e029e17f55decbbf4812c793aaa",
    )
    version(
        "8.1.23",
        sha256="9ea85f8bcc623fd5c8d6b46dec776a90c8c8d9a85abb43d3836eb89697e6e5b8",
    )
    version(
        "8.1.21",
        sha256="44ba43d31721031d54bdce5b722ed0cd7f3bc39dae08141b93b2e779b7900e4e",
    )
    version(
        "8.1.18",
        sha256="5ac6b0877fd0f6afaaf391fffef41daf4d3150edc3250721c9abd4ded6b58486",
    )

    variant("cuda", default=False)
    variant("rocm", default=False)
    conflicts("+cuda", when="+rocm", msg="Pick either CUDA or ROCM")

    # Fix up binaries with patchelf.
    depends_on("patchelf", type="build")

    conflicts("+cuda", when="+rocm", msg="Pick either CUDA or ROCM")

    with when("+cuda"):
        # libcudart.so.11.0
        depends_on("cuda@11.0:11", type="link")

    with when("+rocm"):
        # libamdhip64.so.5
        depends_on("hip@5:", type="link")
        # libhsa-runtime64.so.1
        depends_on("hsa-rocr-dev", type="link")

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
        if "+cuda" in self.spec:
            return find_libraries("libmpi_gtl_cuda", root=self.prefix, shared=True)
        if "+rocm" in self.spec:
            return find_libraries("libmpi_gtl_hsa", root=self.prefix, shared=True)

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
                # The C compiler wrapper can fail because libmpi_gtl_cuda refers to the symbol
                # __gxx_personality_v0 but wasn't linked against libstdc++.
                if "libmpi_gtl_cuda.so" in str(f):
                    patchelf("--add-needed", "libstdc++.so", f, fail_on_error=False)
