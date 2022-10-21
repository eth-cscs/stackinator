# Copyright 2013-2022 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os

import spack.compilers
from spack.package import *


class CrayMpichBinary(Package):
    """Install cray-mpich as a binary package"""

    homepage = "https://www.hpe.com/us/en/compute/hpc/hpc-software.html"
    url = "https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-mpich-8.1.18.4-gcc.tar.gz"

    maintainers = ["haampie"]

    version(
        "8.1.18.4-gcc", sha256="3e7d8c562e4d210a9658f35a7f5fbf23e550e1b9e57b6df6b99adbec7d983903"
    )
    version(
        "8.1.18.4-nvhpc", sha256="d0049c7acf4e90c16c1f169f1f96913e786c5d4cf98230deb51af158664c9b50"
    )

    provides("mpi")

    # Fix up binaries with patchelf.
    depends_on("patchelf", type="build")

    # libcudart.so.11.0
    depends_on("cuda@11.0:11", type="link")

    # libfabric.so.1
    depends_on("libfabric@1:", type="link")

    # Conflicts for gcc
    with when("@8.1.18.4-gcc"):
        # libgfortran.so.5
        conflicts("%gcc@:7")
        for __compiler in spack.compilers.supported_compilers():
            if __compiler != "gcc":
                conflicts("%{}".format(__compiler), msg="gcc required")

    # Conflicts for nvhpc
    with when("@8.1.18.4-nvhpc"):
        conflicts("%nvhpc@:20.6")
        for __compiler in spack.compilers.supported_compilers():
            if __compiler != "nvhpc":
                conflicts("%{}".format(__compiler), msg="nvhpc required")

    # TODO: libpals.so.0? no clue where it comes from.

    def setup_run_environment(self, env):
        env.set("MPICC", join_path(self.prefix.bin, "mpicc"))
        env.set("MPICXX", join_path(self.prefix.bin, "mpic++"))
        env.set("MPIF77", join_path(self.prefix.bin, "mpif77"))
        env.set("MPIF90", join_path(self.prefix.bin, "mpif90"))

    def setup_dependent_build_environment(self, env, dependent_spec):
        self.setup_run_environment(env)
        env.set("MPICH_CC", dependent_spec.package.module.spack_cc)
        env.set("MPICH_CXX", dependent_spec.package.module.spack_cxx)
        env.set("MPICH_FC", dependent_spec.package.module.spack_fc)

    def setup_dependent_package(self, module, dependent_spec):
        self.spec.mpicc = join_path(self.prefix.bin, "mpicc")
        self.spec.mpicxx = join_path(self.prefix.bin, "mpic++")
        self.spec.mpifc = join_path(self.prefix.bin, "mpif90")
        self.spec.mpif77 = join_path(self.prefix.bin, "mpif77")

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

    @run_after("install")
    def fixup_compiler_paths(self):
        filter_file("@@CC@@", self.compiler.cc, self.prefix.bin.mpicc, string=True)
        filter_file("@@CXX@@", self.compiler.cxx, self.prefix.bin.mpicxx, string=True)
        filter_file("@@FC@@", self.compiler.fc, self.prefix.bin.mpifort, string=True)

        filter_file("@@PREFIX@@", self.prefix, self.prefix.bin.mpicc, string=True)
        filter_file("@@PREFIX@@", self.prefix, self.prefix.bin.mpicxx, string=True)
        filter_file("@@PREFIX@@", self.prefix, self.prefix.bin.mpifort, string=True)
