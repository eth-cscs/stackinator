# Copyright 2013-2023 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os
import platform

import spack.compilers
from spack.package import *

_versions = {
    "8.1.29": {
        "Linux-aarch64": "2fc5d1f5743f9cecc0b5dbf13355c25014f96db2386b5c2c2d8495a57b279381",
    },
    "8.1.28": {
        "Linux-aarch64": "dfd6c685adfbf070fe9d546d95b31e108ee7089a738447fa7326973a3e696e8d",
        "Linux-x86_64": "55a0a068bd8bff14f302c5371d7e2b4cf732d5c1ec875bb03e375644e1a6beab",
    },
    "8.1.27": {
        "Linux-x86_64": "5d59cc69b7ae2ef692ae49843bb2c7a44b5a8478d72eaf2ab1f1f6c5983eee0b"
    },
    "8.1.26": {
        "Linux-x86_64": "d308cf3e254ce5873af6caee5ec683a397fed5ce92975f57e5c9215a98d8edad"
    },
    "8.1.25": {
        "Linux-x86_64": "024ab0c4526670a37df7e2995172ba264454fd69c05d8ffe140c9e519397a65c"
    },
    "8.1.24": {
        "Linux-x86_64": "2c3fa339511ed822892e112d3e4d5a39a634d00a31cf22e02ce843f0efcc5ae8"
    },
    "8.1.23": {
        "Linux-x86_64": "ed7ff286ede30ea96dede4c53aa2ef98e8090c988a0bea764cd505ba5fcc0520"
    },
    "8.1.21": {
        "Linux-x86_64": "5fda115f356c26e5d9f8cc68fe578e954a70edd10ebf007182d945345886b61a"
    },
    "8.1.18": {
        "Linux-x86_64": "f7feafd204502d0dab449ff22da138c933ec22d7de3d5e30fbb9a62fc9cdf237"
    },
}


class CrayMpich(Package):
    """Install cray-mpich as a binary package"""

    """Intended to override the main cray-mpich"""

    homepage = "https://www.hpe.com/us/en/compute/hpc/hpc-software.html"
    url = "https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-mpich-8.1.26.tar.gz"
    maintainers = ["bcumming"]
    for ver, packages in _versions.items():
        key = "{0}-{1}".format(platform.system(), platform.machine())
        sha = packages.get(key)
        if sha:
            version(
                ver,
                sha256=sha,
                url=f"https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-mpich-{ver}.{platform.machine()}.tar.gz",
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
        "8.1.29",
    ]:
        with when("+cuda"):
            depends_on(f"cray-gtl@{ver} +cuda", type="link", when="@" + ver)
        with when("+rocm"):
            depends_on(f"cray-gtl@{ver} +rocm", type="link", when="@" + ver)

    depends_on("libfabric@1:", type="link")

    depends_on("cray-pmi", type="link")
    depends_on("xpmem", type="link")

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
                patchelf("--add-needed", "libxpmem.so", f, fail_on_error=False)
                if "+cuda" in self.spec:
                    patchelf("--add-needed", "libmpi_gtl_cuda.so", f, fail_on_error=False)
                if "+rocm" in self.spec:
                    patchelf("--add-needed", "libmpi_gtl_hsa.so", f, fail_on_error=False)

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
