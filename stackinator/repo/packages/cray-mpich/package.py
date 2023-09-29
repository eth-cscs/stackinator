# Copyright 2013-2023 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os

import spack.compilers
from spack.package import *


class CrayMpich(Package):
    """Install cray-mpich as a binary package"""

    """Intended to override the main cray-mpich"""

    homepage = "https://www.hpe.com/us/en/compute/hpc/hpc-software.html"
    url = "https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-mpich-8.1.26.tar.gz"
    maintainers = ["bcumming"]

    version(
        "8.1.26",
        sha256="0f26f7cc691d6378f9eddc66d896f363bfd2f2a1e40d916aa469d5cc0ae6f486",
    )
    version(
        "8.1.25",
        sha256="98dcd4ff715a8e8f1af9e9c4732a671d7d5241ce3bc6ecfa463e570b19f969ff",
    )
    version(
        "8.1.24",
        sha256="2d77b39a5399143d3b31de025515d0bd557dd9ea9ba152b9ef5ff6f6b39eed4b",
    )
    version(
        "8.1.23",
        sha256="e56a5cd2aea3418638c121efc5e4a0ae3b369a2a45b9afc07c5e2086a59f35d7",
    )
    version(
        "8.1.21",
        sha256="ea8921a2f08b0a85e35c2123235f09d2f86d9b092f32f72c5e025e8c5264732e",
    )
    version(
        "8.1.18",
        sha256="45d519be217cea89c58893d25826b15d99183247d15ecee9c3f64913660d79c2",
    )

    variant("cuda", default=False)
    variant("rocm", default=False)

    conflicts("+cuda", when="+rocm", msg="Pick either CUDA or ROCM")

    provides("mpi")

    # Fix up binaries with patchelf.
    depends_on("patchelf", type="build")

    for ver in ["8.1.18", "8.1.21", "8.1.23", "8.1.24", "8.1.25", "8.1.26"]:
        with when("+cuda"):
            depends_on(f"cray-gtl@{ver} +cuda", type="link", when="@" + ver)
        with when("+rocm"):
            depends_on(f"cray-gtl@{ver} +rocm", type="link", when="@" + ver)

    depends_on("libfabric@1:", type="link")

    depends_on("cray-pmi@6.1.11", type="link", when="@8.1.26")
    depends_on("cray-pmi@6.1.10", type="link", when="@8.1.25")
    depends_on("cray-pmi@6.1.9", type="link", when="@8.1.24")
    depends_on("cray-pmi@6.1.8", type="link", when="@8.1.23")
    depends_on("cray-pmi@6.1.7", type="link", when="@8.1.21")
    depends_on("cray-pmi@6.0.17", type="link", when="@8.1.18")

    conflicts("%gcc@:7")

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
        if "%nvhpc" in self.spec:
            install_tree("mpich-nvhpc", prefix)
        elif "%gcc" in self.spec:
            install_tree("mpich-gcc", prefix)

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

        # link with the relevant gtl lib
        if "+cuda" in self.spec:
            lpath = self.spec["cray-gtl"].prefix.lib
            gtl_library = f"-L{lpath} -lmpi_gtl_cuda"
        elif "+rocm" in self.spec:
            lpath = self.spec["cray-gtl"].prefix.lib
            gtl_library = f"-L{lpath} -lmpi_gtl_hsa"
        else:
            gtl_library = ""
        print("==== GTL_LIBRARY", gtl_library)
        filter_file("@@GTL_LIBRARY@@", gtl_library, self.prefix.bin.mpicc, string=True)
        filter_file("@@GTL_LIBRARY@@", gtl_library, self.prefix.bin.mpicxx, string=True)
        filter_file(
            "@@GTL_LIBRARY@@", gtl_library, self.prefix.bin.mpifort, string=True
        )

    @property
    def headers(self):
        hdrs = find_headers("mpi", self.prefix.include, recursive=True)
        hdrs += find_headers(
            "cray_version", self.prefix.include, recursive=True
        )  # cray_version.h
        # cray-mpich depends on cray-pmi
        # hdrs += find_headers("pmi", self.prefix.include, recursive=True) # See cray-pmi package
        hdrs.directories = os.path.dirname(hdrs[0])
        return hdrs

    @property
    def libs(self):
        query_parameters = self.spec.last_query.extra_parameters

        libraries = ["libmpi", "libmpich"]

        if "f77" in query_parameters:
            libraries.extend(["libmpifort", "libmpichfort", "libfmpi", "libfmpich"])

        if "f90" in query_parameters:
            libraries.extend(["libmpif90", "libmpichf90"])

        libs = []
        for lib_folder in [self.prefix.lib, self.prefix.lib64]:
            libs += find_libraries(libraries, root=lib_folder, recursive=True)
            # cray-mpich depends on cray-pmi
            # libs += find_libraries("libpmi", root=lib_folder, recursive=True)
            libs += find_libraries("libopa", root=lib_folder, recursive=True)
            libs += find_libraries("libmpl", root=lib_folder, recursive=True)

        return libs
