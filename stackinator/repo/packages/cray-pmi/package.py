# Copyright 2013-2023 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os
import platform

import spack.compilers
from spack.package import *

_versions = {
    "6.1.14": {
        "Linux-aarch64": "763933310db675c3e690c9a121778c2ddc3a0b8672cb718542888e31099e25c7",
    },
    "6.1.13": {
        "Linux-aarch64": "f865f410145a66bb05520c32ee5b64b6dfcb9ae33aace6d3db5f870e4f4714bc",
        "Linux-x86_64": "217ac554cf84a4c7f08cd149c6a18428e1e3533d73e350fa291b6800895b632e",
    },
    "6.1.12": {
        "Linux-x86_64": "d1a4bd929b73197823dd9b4bcb3c8ef06d80326297a07291b24e5996b60330a8"
    },
    "6.1.11": {
        "Linux-x86_64": "5ebcece6a610da02cd41a9a386fd7463ee909bd55e3370d6d372603f90be9afe"
    },
    "6.1.10": {
        "Linux-x86_64": "f4fbe75c201a171dcfe6ada773a4bf0c606767a0b7a8a76fd19d10852abe1290"
    },
    "6.1.9": {
        "Linux-x86_64": "8fd4194c6c5167f8b81b1cf9b76341669e40d647d0caecef287be6f0f5d95290"
    },
    "6.1.8": {
        "Linux-x86_64": "6c7e5d3038e26b9d0e82428b25b570d00401a6fc9f2fd3c008f15a253a8e2305"
    },
    "6.1.7": {
        "Linux-x86_64": "574b21bd6f8970521c2bc4f096aced896fec8b749f854272cc7bbb7130ae92d8"
    },
    "6.0.17": {
        "Linux-x86_64": "5f15cd577c6c082888fcf0f76f0f5a898ddfa32370e1c32ffe926912d4d4dad0"
    },
}


class CrayPmi(Package):
    """Install cray-pmi"""

    """Intended to override the main cray-pmi"""

    homepage = "https://www.hpe.com/us/en/compute/hpc/hpc-software.html"
    url = "https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-pmi-6.1.11.tar.gz"
    maintainers = ["bcumming", "simonpintarelli"]

    for ver, packages in _versions.items():
        key = "{0}-{1}".format(platform.system(), platform.machine())
        sha = packages.get(key)
        if sha:
            version(
                ver,
                sha256=sha,
                url=f"https://jfrog.svc.cscs.ch/artifactory/cray-mpich/cray-pmi-{ver}.{platform.machine()}.tar.gz",
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
