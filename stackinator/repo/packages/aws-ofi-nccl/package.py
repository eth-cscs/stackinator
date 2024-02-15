# Copyright 2013-2024 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

from spack.package import *


class AwsOfiNccl(AutotoolsPackage):
    """AWS OFI NCCL is a plug-in which enables EC2 developers to use
    libfabric as a network provider while running NVIDIA's NCCL based
    applications."""

    homepage = "https://github.com/aws/aws-ofi-nccl"
    git = "https://github.com/aws/aws-ofi-nccl.git"
    url = "https://github.com/aws/aws-ofi-nccl.git"

    maintainers("bvanessen")

    version("master", branch="master")
    version("v1.7.4",
            sha256="cca529da330d3155ae1502c21365d62159254bca6bfc0482afd35e7eaa927090",
            url="https://github.com/aws/aws-ofi-nccl/releases/download/v1.7.4-aws/aws-ofi-nccl-1.7.4-aws.tar.gz",
    )

    variant("trace", default=False, description="Enable printing trace messages")
    variant("tests", default=False, description="Build tests")

    depends_on("libfabric")
    depends_on("cuda")
    depends_on("nccl")
    depends_on("mpi")
    depends_on("hwloc")
    depends_on("autoconf", type="build")
    depends_on("automake", type="build")
    depends_on("libtool", type="build")

    # To enable this plug-in to work with NCCL add it to the LD_LIBRARY_PATH
    def setup_run_environment(self, env):
        aws_ofi_nccl_home = self.spec.prefix
        env.append_path("LD_LIBRARY_PATH", aws_ofi_nccl_home.lib)

    # To enable this plug-in to work with NCCL add it to the LD_LIBRARY_PATH
    def setup_dependent_run_environment(self, env, dependent_spec):
        aws_ofi_nccl_home = self.spec["aws-ofi-nccl"].prefix
        env.append_path("LD_LIBRARY_PATH", aws_ofi_nccl_home.lib)

    def configure_args(self):
        spec = self.spec
        args = []

        # Always set configure's external paths to use the Spack
        # provided dependencies
        args.extend(
            [
                "--with-libfabric={0}".format(spec["libfabric"].prefix),
                "--with-cuda={0}".format(spec["cuda"].prefix),
                "--with-nccl={0}".format(spec["nccl"].prefix),
                "--with-mpi={0}".format(spec["mpi"].prefix),
            ]
        )

        args.extend(self.enable_or_disable("trace"))
        args.extend(self.enable_or_disable("tests"))

        return args
