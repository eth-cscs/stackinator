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
        "8.1.28",
        sha256="d2d2c36b55259826a83d76cc7d0cff2f332fc236088a0d6b8ddf27937ea290f8",
    )
    version(
        "8.1.27",
        sha256="ac3fa0500a734a551f5af1e6987a397513c8f57594a1ffb3f61e00615c1f3224",
    )
    version(
        "8.1.26",
        sha256="2e921d75836699caa21d7a06ba818583ba8de5e170d9405c35122f3fb50b6ec3",
    )
    version(
        "8.1.25",
        sha256="bfd3b0a2dd1a45f50f5ff9f214d0f14e77c1ecf095d14d6fdcee8e5b6cf14d0b",
    )
    version(
        "8.1.24",
        sha256="68f38a2833655e989e6e6187930ed5eaffa2d08cb7db4d7239a229c2f618ac08",
    )
    version(
        "8.1.23",
        sha256="9c452c76c684ec8abef3c666acbb2fb5286e76dfd48117d5dbed6cbb04ed16e4",
    )
    version(
        "8.1.21",
        sha256="41e8b5b1a2ca0777a1dd412df1bbcf602b27568806ee28e3ff891e6b43fd78d1",
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

    for ver in [
        "8.1.18",
        "8.1.21",
        "8.1.23",
        "8.1.24",
        "8.1.25",
        "8.1.26",
        "8.1.27",
        "8.1.28",
    ]:
        with when("+cuda"):
            depends_on(f"cray-gtl@{ver} +cuda", type="link", when="@" + ver)
        with when("+rocm"):
            depends_on(f"cray-gtl@{ver} +rocm", type="link", when="@" + ver)

    depends_on("libfabric@1:", type="link")

    depends_on("cray-pmi", type="link")

    conflicts("%gcc@:7")
    conflicts("%gcc@:11", when="@8.1.28:")

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
            gtl_library = f"-L{lpath} -Wl,-rpath,{lpath} -lmpi_gtl_cuda"
        elif "+rocm" in self.spec:
            lpath = self.spec["cray-gtl"].prefix.lib
            gtl_library = f"-L{lpath} -Wl,-rpath,{lpath}  -lmpi_gtl_hsa"
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
