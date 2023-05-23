import pathlib

import jinja2
import yaml

from . import root_logger, schema


class Mirror:
    def __init__(self, config, source):
        if config:
            enabled = config.get("enable", True)
            key = config.get("key", None)
            self._source = None if not enabled else source
            self._key = key
        else:
            self._source = self._key = None

    @property
    def key(self):
        return self._key

    @property
    def source(self):
        return self._source


class Recipe:
    valid_mpi_specs = {
        "cray-mpich": (None, None),
        "mpich": ("4.1", "device=ch4 netmod=ofi +slurm"),
        "mvapich2": (
            "3.0a",
            "+xpmem fabrics=ch4ofi ch4_max_vcis=4 process_managers=slurm",
        ),
    }

    def __init__(self, args):
        self._logger = root_logger
        self._logger.debug("Generating recipe")
        path = pathlib.Path(args.recipe)
        if not path.is_absolute():
            path = pathlib.Path.cwd() / path

        if not path.is_dir():
            raise FileNotFoundError(f"The recipe path '{path}' does not exist")

        self.path = path
        self.root = pathlib.Path(__file__).parent.resolve()

        # required compiler.yaml file
        compiler_path = path / "compilers.yaml"
        self._logger.debug(f"opening {compiler_path}")
        if not compiler_path.is_file():
            raise FileNotFoundError(
                f"The recipe path '{compiler_path}' does " f"not contain compilers.yaml"
            )

        with compiler_path.open() as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            if "compilers" in raw:
                self._logger.warning(
                    f"{compiler_path} uses deprecated 'compilers:' "
                    f"header. This will be an error in future releases."
                )
                raw = raw["compilers"]
            schema.compilers_validator.validate(raw)
            self.generate_compiler_specs(raw)

        # required environments.yaml file
        environments_path = path / "environments.yaml"
        self._logger.debug(f"opening {environments_path}")
        if not environments_path.is_file():
            raise FileNotFoundError(
                f"The recipe path '{environments_path}' does "
                f" not contain environments.yaml"
            )

        with environments_path.open() as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            schema.environments_validator.validate(raw)
            self.generate_environment_specs(raw)

        # required config.yaml file
        config_path = path / "config.yaml"
        self._logger.debug(f"opening {config_path}")
        if not config_path.is_file():
            raise FileNotFoundError(
                f"The recipe path '{config_path}' does " f"not contain compilers.yaml"
            )

        with config_path.open() as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            schema.config_validator.validate(raw)
            self.config = raw

        # override the system target
        if args.system:
            self.config["system"] = args.system

        # optional modules.yaml file
        modules_path = path / "modules.yaml"
        self._logger.debug(f"opening {modules_path}")
        if not modules_path.is_file():
            modules_path = (
                pathlib.Path(args.build) / "spack/etc/spack/defaults/modules.yaml"
            )
            self._logger.debug(f"no modules.yaml provided - using the {modules_path}")

        self.modules = modules_path
        if not self.configs_path.is_dir():
            raise FileNotFoundError(
                f"The system {self.config['system']!r} is not a supported cluster"
            )

        # optional packages.yaml file
        packages_path = path / "packages.yaml"
        self._logger.debug(f"opening {packages_path}")
        self.packages = None
        if packages_path.is_file():
            with packages_path.open() as fid:
                self.packages = yaml.load(fid, Loader=yaml.Loader)

        # Select location of the mirrors.yaml file to use.
        # Look first in the recipe path, then in the system configuration path.
        mirrors_path = path / "mirrors.yaml"
        mirrors_source = mirrors_path if mirrors_path.is_file() else None
        if mirrors_source is None:
            mirrors_path = self.configs_path / "mirrors.yaml"
            mirrors_source = mirrors_path if mirrors_path.is_file() else None

        self._mirror = Mirror(config=self.config["mirror"], source=mirrors_source)

    @property
    def mirror(self):
        return self._mirror

    def generate_modules(self):
        with self.modules.open() as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            raw["modules"]["default"]["roots"]["tcl"] = (
                pathlib.Path(self.config["store"]) / "modules"
            ).as_posix()
            return yaml.dump(raw)

    # creates the self.environments field that describes the full specifications
    # for all of the environments sets, grouped in environments, from the raw
    # environments.yaml input.
    def generate_environment_specs(self, raw):
        environments = raw

        # enumerate large binary packages that should not be pushed to binary caches
        for _, config in environments.items():
            config["exclude_from_cache"] = ["cuda"]

        # check the environment descriptions and ammend where features are missing
        for name, config in environments.items():
            if ("specs" not in config) or (config["specs"] is None):
                environments[name]["specs"] = []

            if "mpi" not in config:
                environments[name]["mpi"] = {"spec": None, "gpu": None}

        for name, config in environments.items():
            if config["mpi"]:
                mpi = config["mpi"]
                mpi_spec = mpi["spec"]
                mpi_gpu = mpi["gpu"]
                if mpi_spec:
                    try:
                        mpi_impl, mpi_ver = mpi_spec.strip().split(sep="@", maxsplit=1)
                    except ValueError:
                        mpi_impl = mpi_spec.strip()
                        mpi_ver = None

                    if mpi_impl in Recipe.valid_mpi_specs:
                        default_ver, options = Recipe.valid_mpi_specs[mpi_impl]
                        if mpi_ver:
                            version_opt = f"@{mpi_ver}"
                        else:
                            version_opt = f"@{default_ver}" if default_ver else ""

                        spec = f"{mpi_impl}{version_opt} {options or ''}".strip()

                        if mpi_gpu:
                            if mpi_impl != "cray-mpich":
                                spec = f"{spec} cuda_arch=80"
                            else:
                                spec = f"{spec} +{mpi_gpu}"

                        environments[name]["specs"].append(spec)
                    else:
                        # TODO: Create a custom exception type
                        raise Exception(f"Unsupported mpi: {mpi_impl}")

        self.environments = environments

    # creates the self.compilers field that describes the full specifications
    # for all of teh compilers from the raw compilers.yaml input
    def generate_compiler_specs(self, raw):
        compilers = {}

        bootstrap = {}
        bootstrap["packages"] = {
            "external": [
                "perl",
                "m4",
                "autoconf",
                "automake",
                "libtool",
                "gawk",
                "python",
                "texinfo",
                "gawk",
            ],
            "variants": {
                "gcc": "[build_type=Release ~bootstrap +strip]",
                "mpc": "[libs=static]",
                "gmp": "[libs=static]",
                "mpfr": "[libs=static]",
                "zstd": "[libs=static]",
                "zlib": "[~shared]",
            },
        }
        bootstrap_spec = raw["bootstrap"]["spec"]
        bootstrap["specs"] = [
            f"{bootstrap_spec} languages=c,c++",
            "squashfs default_compression=zstd",
        ]
        bootstrap["exclude_from_cache"] = []
        compilers["bootstrap"] = bootstrap

        gcc = {}
        gcc["packages"] = {
            "external": [
                "perl",
                "m4",
                "autoconf",
                "automake",
                "libtool",
                "gawk",
                "python",
                "texinfo",
                "gawk",
            ],
            "variants": {
                "gcc": "[build_type=Release +profiled +strip]",
                "mpc": "[libs=static]",
                "gmp": "[libs=static]",
                "mpfr": "[libs=static]",
                "zstd": "[libs=static]",
                "zlib": "[~shared]",
            },
        }
        gcc["specs"] = raw["gcc"]["specs"]
        gcc["requires"] = bootstrap_spec
        gcc["exclude_from_cache"] = []
        compilers["gcc"] = gcc
        if raw["llvm"] is not None:
            llvm = {}
            llvm["packages"] = False
            llvm["specs"] = []
            for spec in raw["llvm"]["specs"]:
                if spec.startswith("nvhpc"):
                    llvm["specs"].append(f"{spec}~mpi~blas~lapack")

                if spec.startswith("llvm"):
                    llvm["specs"].append(
                        f"{spec} +clang targets=x86 ~gold ^ninja@kitware"
                    )

            llvm["requires"] = raw["llvm"]["requires"]
            llvm["exclude_from_cache"] = ["nvhpc"]
            compilers["llvm"] = llvm

        self.compilers = compilers

    # The path of the default configuration for the target system/cluster
    @property
    def configs_path(self):
        system = self.config["system"]
        return self.root / "cluster-config" / system

    # Boolean flag that indicates whether the recipe is configured to use
    # a binary cache.
    def generate_compilers(self):
        files = {}

        template_path = self.root / "templates"
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        makefile_template = env.get_template("Makefile.compilers")
        push_to_cache = self.mirror.source and self.mirror.key
        files["makefile"] = makefile_template.render(
            compilers=self.compilers, push_to_cache=push_to_cache
        )

        # generate compilers/<compiler>/spack.yaml
        files["config"] = {}
        for compiler, config in self.compilers.items():
            spack_yaml_template = env.get_template(f"compilers.{compiler}.spack.yaml")
            files["config"][compiler] = spack_yaml_template.render(config=config)

        return files

    def generate_environments(self):
        files = {}

        template_path = self.root / "templates"
        jenv = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        makefile_template = jenv.get_template("Makefile.environments")
        push_to_cache = self.mirror.source and self.mirror.key
        files["makefile"] = makefile_template.render(
            environments=self.environments, push_to_cache=push_to_cache
        )

        files["config"] = {}
        for env, config in self.environments.items():
            spack_yaml_template = jenv.get_template("environments.spack.yaml")
            files["config"][env] = spack_yaml_template.render(config=config)

        return files
