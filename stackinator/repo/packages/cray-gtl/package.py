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
        "8.1.28",
        sha256="2e82c618648e79bdc4b8bf9394be8fd59c34ccd77f172afd11fce38beca1ecab",
    )
    version(
        "8.1.27",
        sha256="c00836641c7d1f40300f8e4b068a1ba1ff4b0ca31af24b9507d768fc6fe5753c",
    )
    version(
        "8.1.26",
        sha256="37d9626cb5f851f63c9799c18a419354c6f21c77f90558472552156df9eef311",
    )
    version(
        "8.1.25",
        sha256="a2e2af2037e63b64ef74d870c0bab91a8109e75eef82a30250b81b0d785ff6ae",
    )
    version(
        "8.1.24",
        sha256="2fa8635f829e67844e7b30dffb092a336d257e0e769d2225030f2ccf4c1d302f",
    )
    version(
        "8.1.23",
        sha256="034667c2ea49eec76ef8f79494231bad94884b99683edabf781beed01ec681e4",
    )
    version(
        "8.1.21",
        sha256="78072edfcb6cc24cfefab06e824111b5b2b839551235ece68cd154bec7936a24",
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
        depends_on("cuda@11.0:11", type="link", when="@:8.1.27")
        depends_on("cuda@12:", type="link", when="@8.1.28:")

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
