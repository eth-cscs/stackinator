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


    version("8.1.23-gcc",
            sha256="2d1dfda811848d278548b0d7735f17341c70380dbf7f91dc680e5afcfb5e0038",
            url="https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-mpich-8.1.23-gcc.tar.gz")
    version("8.1.23-nvhpc",
            sha256="1dd9b161c538dbac564ecff6f1552220ba40dcc9436dc855087438f29861eba1",
            url="https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-mpich-8.1.23-nvhpc.tar.gz")
    version("8.1.21.1-gcc",
            sha256="0a6852ebf06afd249285fd09566e8489300cba96ad66e90c40df36b6af9a631e",
            url="https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-mpich-8.1.21.1-gcc.tar.gz")
    version("8.1.21.1-nvhpc",
            sha256="791b39f2ecb933060abaa8c8704e71da01c6962c4211cc99d12b9d964e9be4cb",
            url="https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-mpich-8.1.21.1-nvhpc.tar.gz")
    version("8.1.18.4-gcc",
            sha256="776c695aeed62b3f64a1bca11b30a2537a907777a8664d2f092e3deac288e4ad",
            url="https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-mpich-8.1.18.4-gcc.tar.gz")
    version("8.1.18.4-nvhpc",
            sha256="2285433363c75a04ccdf4798be5b0e296e0c9a8fb8fcb38eb0aa4ccf8d1e0843",
            url="https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-mpich-8.1.18.4-nvhpc.tar.gz")


    variant("cuda", default=False)
    variant("rocm", default=False)

    conflicts("+cuda", when="+rocm", msg="Pick either CUDA or ROCM")

    provides("mpi")

    # Fix up binaries with patchelf.
    depends_on("patchelf", type="build")
    with when("+cuda"):
        # libcudart.so.11.0
        depends_on("cuda@11.0:11", type="link")

    with when("+rocm"):
        # libamdhip64.so.5
        depends_on("hip@5:", type="link")
        # libhsa-runtime64.so.1
        depends_on("hsa-rocr-dev", type="link")

    # libfabric.so.1
    depends_on("libfabric@1:", type="link")

    with when("@8.1.23-gcc"):
        # libgfortran.so.5
        conflicts("%gcc@:7")
        for __compiler in spack.compilers.supported_compilers():
            if __compiler != "gcc":
                conflicts("%{}".format(__compiler), msg="gcc required")

    with when("@8.1.23-nvhpc"):
        conflicts("%nvhpc@:20.6")
        conflicts("+rocm")
        conflicts("~cuda")
        for __compiler in spack.compilers.supported_compilers():
            if __compiler != "nvhpc":
                conflicts("%{}".format(__compiler), msg="nvhpc required")

    with when("@8.1.21.1-gcc"):
        # libgfortran.so.5
        conflicts("%gcc@:7")
        for __compiler in spack.compilers.supported_compilers():
            if __compiler != "gcc":
                conflicts("%{}".format(__compiler), msg="gcc required")

    with when("@8.1.21.1-nvhpc"):
        conflicts("%nvhpc@:20.6")
        conflicts("+rocm")
        conflicts("~cuda")
        for __compiler in spack.compilers.supported_compilers():
            if __compiler != "nvhpc":
                conflicts("%{}".format(__compiler), msg="nvhpc required")

    with when("@8.1.18.4-gcc"):
        # libgfortran.so.5
        conflicts("%gcc@:7")
        for __compiler in spack.compilers.supported_compilers():
            if __compiler != "gcc":
                conflicts("%{}".format(__compiler), msg="gcc required")

    with when("@8.1.18.4-nvhpc"):
        conflicts("%nvhpc@:20.6")
        conflicts("+rocm")
        conflicts("~cuda")
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
                # The C compiler wrapper can fail because libmpi_gtl_cuda refers to the symbol
                # __gxx_personality_v0 but wasn't linked against libstdc++.
                if "libmpi_gtl_cuda.so" in str(f):
                    patchelf("--add-needed", "libstdc++.so", f, fail_on_error=False)

    @run_after("install")
    def fixup_compiler_paths(self):
        filter_file("@@CC@@", self.compiler.cc, self.prefix.bin.mpicc, string=True)
        filter_file("@@CXX@@", self.compiler.cxx, self.prefix.bin.mpicxx, string=True)
        filter_file("@@FC@@", self.compiler.fc, self.prefix.bin.mpifort, string=True)

        filter_file("@@PREFIX@@", self.prefix, self.prefix.bin.mpicc, string=True)
        filter_file("@@PREFIX@@", self.prefix, self.prefix.bin.mpicxx, string=True)
        filter_file("@@PREFIX@@", self.prefix, self.prefix.bin.mpifort, string=True)

        # link with the relevant gtl lib
        if "+cuda" in self.spec:
            gtl_library = "-lmpi_gtl_cuda"
        elif "+rocm" in self.spec:
            gtl_library = "-lmpi_gtl_hsa"
        else:
            gtl_library = ""

        filter_file("@@GTL_LIBRARY@@", gtl_library, self.prefix.bin.mpicc, string=True)
        filter_file("@@GTL_LIBRARY@@", gtl_library, self.prefix.bin.mpicxx, string=True)
        filter_file("@@GTL_LIBRARY@@", gtl_library, self.prefix.bin.mpifort, string=True)
