import copy
import pathlib
import re

import jinja2
from ruamel.yaml import YAML

from . import cache, root_logger, schema, spack_util
from .etc import envvars

yaml = YAML()


class Recipe:
    @property
    def path(self):
        """the path of the recipe"""
        return self._path

    @path.setter
    def path(self, recipe_path):
        path = pathlib.Path(recipe_path)
        if not path.is_absolute():
            path = pathlib.Path.cwd() / path

        if not path.is_dir():
            raise FileNotFoundError(f"The recipe path '{path}' does not exist")

        self._path = path

    def __init__(self, args):
        self._logger = root_logger
        self._logger.debug("Generating recipe")

        self.no_bwrap = args.no_bwrap

        # set the system configuration path
        self.system_config_path = args.system

        # set the recipe path
        self.path = args.recipe

        self.template_path = pathlib.Path(__file__).parent.resolve() / "templates"

        # required config.yaml file
        self.config = self.path / "config.yaml"

        # override the mount point if defined as a CLI argument
        if args.mount:
            self.config["store"] = args.mount

        # ensure that the requested mount point exists
        if not self.mount.is_dir():
            raise FileNotFoundError(f"the mount point '{self.mount}' must exist")

        # required compilers.yaml file
        compiler_path = self.path / "compilers.yaml"
        self._logger.debug(f"opening {compiler_path}")
        if not compiler_path.is_file():
            raise FileNotFoundError(f"The recipe path '{compiler_path}' does not contain compilers.yaml")

        with compiler_path.open() as fid:
            raw = yaml.load(fid)
            schema.CompilersValidator.validate(raw)
            self.generate_compiler_specs(raw)

        # optional modules.yaml file
        modules_path = self.path / "modules.yaml"
        self._logger.debug(f"opening {modules_path}")
        if not modules_path.is_file():
            modules_path = pathlib.Path(args.build) / "spack/etc/spack/defaults/modules.yaml"
            self._logger.debug(f"no modules.yaml provided - using the {modules_path}")

        self.modules = modules_path

        # optional packages.yaml file
        packages_path = self.path / "packages.yaml"
        self._logger.debug(f"opening {packages_path}")
        self.packages = None
        if packages_path.is_file():
            with packages_path.open() as fid:
                self.packages = yaml.load(fid)

        self._logger.debug("creating packages")

        # load recipe/packages.yaml -> recipe_packages (if it exists)
        recipe_packages = {}
        recipe_packages_path = self.path / "packages.yaml"
        if recipe_packages_path.is_file():
            with recipe_packages_path.open() as fid:
                raw = yaml.load(fid)
                recipe_packages = raw["packages"]

        # load system/packages.yaml -> system_packages (if it exists)
        system_packages = {}
        system_packages_path = self.system_config_path / "packages.yaml"
        if system_packages_path.is_file():
            # load system yaml
            with system_packages_path.open() as fid:
                raw = yaml.load(fid)
                system_packages = raw["packages"]

        # extract gcc packages from system packages
        # remove gcc from packages afterwards
        if "gcc" in system_packages:
            gcc_packages = {"gcc": system_packages["gcc"]}
            del system_packages["gcc"]
        else:
            raise RuntimeError("The system packages.yaml file does not provide gcc")

        # load the optional network.yaml from system config:
        # - meta data about mpi
        # - package information for network libraries (libfabric, openmpi, cray-mpich, ... etc)
        network_path = self.system_config_path / "network.yaml"
        network_packages = {}
        mpi_templates = {}
        if network_path.is_file():
            self._logger.debug(f"opening {network_path}")
            with network_path.open() as fid:
                raw = yaml.load(fid)
                if "packages" in raw:
                    network_packages = raw["packages"]
                if "mpi" in raw:
                    mpi_templates = raw["mpi"]
        self.mpi_templates = mpi_templates

        # note that the order that package sets are specified in is significant.
        # arguments to the right have higher precedence.
        self.packages = {
            # the package definition used in every environment
            "global": {"packages": system_packages | network_packages | recipe_packages},
            # the package definition used to build gcc (requires system gcc to bootstrap)
            "gcc": {"packages": system_packages | gcc_packages | recipe_packages},
        }

        # required environments.yaml file
        environments_path = self.path / "environments.yaml"
        self._logger.debug(f"opening {environments_path}")
        if not environments_path.is_file():
            raise FileNotFoundError(f"The recipe path '{environments_path}' does not contain environments.yaml")

        with environments_path.open() as fid:
            raw = yaml.load(fid)
            # add a special environment that installs tools required later in the build process.
            # currently we only need squashfs for creating the squashfs file.
            raw["uenv_tools"] = {
                "compiler": ["gcc"],
                "network": {"mpi": None, "specs": None},
                "unify": True,
                "duplicates": {"strategy": "minimal"},
                "deprecated": False,
                "specs": ["squashfs"],
                "views": {},
            }
            schema.EnvironmentsValidator.validate(raw)
            self.generate_environment_specs(raw)

        # optional mirror configurtion
        mirrors_path = self.path / "mirrors.yaml"
        if mirrors_path.is_file():
            self._logger.warning(
                "mirrors.yaml have been removed from recipes, use the --cache option on stack-config instead."
            )
            raise RuntimeError("Unsupported mirrors.yaml file in recipe.")

        self.mirror = (args.cache, self.mount)

        # optional post install hook
        if self.post_install_hook is not None:
            self._logger.debug(f"post install hook {self.post_install_hook}")
        else:
            self._logger.debug("no post install hook provided")

        # optional pre install hook
        if self.pre_install_hook is not None:
            self._logger.debug(f"pre install hook {self.pre_install_hook}")
        else:
            self._logger.debug("no pre install hook provided")

        # determine the version of spack being used:
        # currently this just returns 1.0... develop is ignored
        # --develop flag will imply the next release of spack after 1.0 is supported properly
        self.spack_version = self.find_spack_version(args.develop)

    # Returns:
    #   Path: if the recipe contains a spack package repository
    #   None: if there is the recipe contains no repo
    @property
    def spack_repo(self):
        repo_path = self.path / "repo"
        if spack_util.is_repo(repo_path):
            return repo_path
        return None

    # Returns:
    #   Path: of the recipe extra path if it exists
    #   None: if there is no user-provided extra path in the recipe
    @property
    def user_extra(self):
        extra_path = self.path / "extra"
        if extra_path.exists() and extra_path.is_dir():
            return extra_path
        return None

    # Returns:
    #   Path: of the recipe post install script if it was provided
    #   None: if there is no user-provided post install script
    @property
    def post_install_hook(self):
        hook_path = self.path / "post-install"
        if hook_path.exists() and hook_path.is_file():
            return hook_path
        return None

    # Returns:
    #   Path: of the recipe pre install script if it was provided
    #   None: if there is no user-provided pre install script
    @property
    def pre_install_hook(self):
        hook_path = self.path / "pre-install"
        if hook_path.exists() and hook_path.is_file():
            return hook_path
        return None

    # Returns a dictionary with the following fields
    #
    # root: /path/to/cache
    # path: /path/to/cache/user-environment
    # key: /path/to/private-pgp-key
    @property
    def mirror(self):
        return self._mirror

    # configuration is a tuple with two fields:
    # - a Path of the yaml file containing the cache configuration
    # - the mount point of the image
    @mirror.setter
    def mirror(self, configuration):
        self._logger.debug(f"configuring build cache mirror with {configuration}")
        self._mirror = None

        file, mount = configuration

        if file is not None:
            mirror_config_path = pathlib.Path(file)
            if not mirror_config_path.is_file():
                raise FileNotFoundError(f"The cache configuration '{file}' is not a file")

            self._mirror = cache.configuration_from_file(mirror_config_path, pathlib.Path(mount))

    @property
    def config(self):
        return self._config

    @config.setter
    def config(self, config_path):
        self._logger.debug(f"opening {config_path}")
        if not config_path.is_file():
            raise FileNotFoundError(f"The recipe path '{config_path}' does not contain config.yaml")

        with config_path.open() as fid:
            raw = yaml.load(fid)
            schema.ConfigValidator.validate(raw)
            self._config = raw

    # In Stackinator 6 we replaced logic required to determine the
    # pre 1.0 Spack version.
    def find_spack_version(self, develop):
        return "1.0"

    @property
    def environment_view_meta(self):
        # generate the view meta data that is presented in the squashfs image meta data
        view_meta = {}
        for _, env in self.environments.items():
            for view in env["views"]:
                ev_inputs = view["extra"]["env_vars"]
                env = envvars.EnvVarSet()

                # TODO: one day this code will be revisited because we need to append_path
                # or prepend_path to a variable that isn't in envvars.is_list_var
                # On that day, extend the environments.yaml views:uenv:env_vars field
                # to also accept a list of env var names to add to the blessed list of prefix paths

                for v in ev_inputs["set"]:
                    ((name, value),) = v.items()
                    # insist that the only 'set' operation on prefix variables is to unset/reset them
                    # this requires that users use append and prepend to build up the variables
                    if envvars.is_list_var(name) and value is not None:
                        raise RuntimeError(f"{name} in the {view['name']} view is a prefix variable.")
                    else:
                        if envvars.is_list_var(name):
                            env.set_list(name, [], envvars.EnvVarOp.SET)
                        else:
                            env.set_scalar(name, value)

                for v in ev_inputs["prepend_path"]:
                    ((name, value),) = v.items()
                    if not envvars.is_list_var(name):
                        raise RuntimeError(f"{name} in the {view['name']} view is not a known prefix path variable")
                    env.set_list(name, [value], envvars.EnvVarOp.APPEND)

                for v in ev_inputs["append_path"]:
                    ((name, value),) = v.items()
                    if not envvars.is_list_var(name):
                        raise RuntimeError(f"{name} in the {view['name']} view is not a known prefix path variable")
                    env.set_list(name, [value], envvars.EnvVarOp.PREPEND)

                view_meta[view["name"]] = {
                    "root": view["config"]["root"],
                    "activate": view["config"]["root"] + "/activate.sh",
                    "description": "",  # leave the description empty for now
                    "recipe_variables": env.as_dict(),
                }

        return view_meta

    @property
    def modules_yaml_data(self):
        with self.modules.open() as fid:
            raw = yaml.load(fid)
            raw["modules"]["default"]["roots"]["tcl"] = (pathlib.Path(self.mount) / "modules").as_posix()
            return raw

    # creates the self.environments field that describes the full specifications
    # for all of the environments sets, grouped in environments, from the raw
    # environments.yaml input.
    def generate_environment_specs(self, raw):
        environments = raw

        # enumerate large binary packages that should not be pushed to binary caches
        for _, config in environments.items():
            config["exclude_from_cache"] = ["cuda", "nvhpc", "perl"]

        # check the environment descriptions and ammend where features are missing
        for name, config in environments.items():
            if ("specs" not in config) or (config["specs"] is None):
                environments[name]["specs"] = []

        # Complete configuration of MPI in each environment
        # this involves generate specs for the chosen MPI implementation
        # and (optionally) additional dependencies like libfabric, which are
        # appended to the list of specs in the environment.
        for name, config in environments.items():
            # the "mpi" entry records the name of the MPI implementation used by the environment.
            # set it to none by default, and have it set if the config["network"] description specifies
            # an MPI implementation.
            environments[name]["mpi"] = None

            if config["network"]:
                # we will build a list of additional specs related to MPI, libfabric, etc to add to the list of specs
                # in the generated spack.yaml file.
                # start with an empty list:
                specs = []

                if config["network"]["mpi"] is not None:
                    spec = config["network"]["mpi"].strip()
                    # find the name of the MPI package
                    match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*)", spec)
                    if match:
                        mpi_name = match.group(1)
                        supported_mpis = [k for k in self.mpi_templates.keys()]
                        if mpi_name not in supported_mpis:
                            raise Exception(f"{mpi_name} is not a supported MPI version: try one of {supported_mpis}.")
                    else:
                        raise Exception(f"{spec} is not a valid MPI spec")

                    # add the mpi spec to the list of explicit specs
                    specs.append(spec)

                    # if the recipe provided explicit specs for dependencies, inject them:
                    if config["network"]["specs"]:
                        specs += config["network"]["specs"]
                    # otherwise inject dependencies from network.yaml (if they exist)
                    elif self.mpi_templates[mpi_name]["specs"]:
                        specs += self.mpi_templates[mpi_name]["specs"]

                    environments[name]["mpi"] = mpi_name
                    environments[name]["specs"] += specs

        # set constraints that ensure the the main compiler is always used to build packages
        # that do not explicitly request a compiler.
        for name, config in environments.items():
            # if the recipe provided no "prefer" settings, provide a default one that
            # nudges Spack towards using the first compiler (we don't think that this actually
            # has much effect).
            # With this set, the user can the customise the compiler to use as on a package spec, e.g.
            #   hdf5+mpi+fortran %fortran=nvhpc
            # Which will compile the upstream MPI with nvfortran, as well as downstream dependendencies.
            if config["prefer"] is None:
                compiler = config["compiler"][0]
                config["prefer"] = [
                    f"%[when=%c] c={compiler} %[when=%cxx] cxx={compiler} %[when=%fortran] fortran={compiler}"
                ]

        # Create all meta data for all of the views.
        env_names = set()
        for name, config in environments.items():
            views = []
            for view_name, vc in config["views"].items():
                if view_name in env_names:
                    raise Exception(f"An environment view with the name '{name}' already exists.")
                env_names.add(view_name)
                view_config = copy.deepcopy(vc)
                # set some default values:
                # ["link"] = "roots"
                # ["uenv"]["add_compilers"] = True
                # ["uenv"]["prefix_paths"] = {}
                # ["uenv"]["env_vars"] = {"set": [], "unset": [], "prepend_path": [], "append_path": []}
                if view_config is None:
                    view_config = {}

                view_config.setdefault("link", "roots")
                view_config.setdefault("uenv", {})
                view_config["uenv"].setdefault("add_compilers", True)
                view_config["uenv"].setdefault("prefix_paths", {})
                view_config["uenv"].setdefault("env_vars", {})
                view_config["uenv"]["env_vars"].setdefault("set", [])
                view_config["uenv"]["env_vars"].setdefault("unset", [])
                view_config["uenv"]["env_vars"].setdefault("prepend_path", [])
                view_config["uenv"]["env_vars"].setdefault("append_path", [])

                prefix_string = ",".join(
                    [f"{pname}={':'.join(paths)}" for pname, paths in view_config["uenv"]["prefix_paths"].items()]
                )
                view_config["uenv"]["prefix_string"] = prefix_string
                view_config["root"] = str(self.mount / "env" / view_name)

                extra = view_config.pop("uenv")
                views.append({"name": view_name, "config": view_config, "extra": extra})

            config["views"] = views

        self.environments = environments

    # creates the self.compilers field that describes the full specifications
    # for all of the compilers from the raw compilers.yaml input
    def generate_compiler_specs(self, raw):
        compilers = {}

        cache_exclude = ["cuda", "nvhpc", "perl"]
        gcc = {}
        # gcc["packages"] = {
        #     "external": [ "perl", "m4", "autoconf", "automake", "libtool", "gawk", "python", "texinfo", "gawk", ],
        # }
        gcc_version = raw["gcc"]["version"]
        gcc["specs"] = [f"gcc@{gcc_version} + bootstrap"]
        gcc["exclude_from_cache"] = []

        compilers["gcc"] = gcc

        if raw["nvhpc"] is not None:
            nvhpc = {}
            nvhpc_version = raw["nvhpc"]["version"]
            nvhpc["packages"] = False
            nvhpc["specs"] = [f"nvhpc@{nvhpc_version} ~mpi~blas~lapack"]

            nvhpc["exclude_from_cache"] = cache_exclude
            compilers["nvhpc"] = nvhpc

        if raw["llvm"] is not None:
            llvm = {}
            llvm_version = raw["llvm"]["version"]
            llvm["packages"] = False
            llvm["specs"] = [f"llvm@{llvm_version} +clang ~gold"]

            llvm["exclude_from_cache"] = cache_exclude
            compilers["llvm"] = llvm

        if raw["llvm-amdgpu"] is not None:
            llvm_amdgpu = {}
            llvm_amdgpu_version = raw["llvm-amdgpu"]["version"]
            llvm_amdgpu["packages"] = False
            llvm_amdgpu["specs"] = [f"llvm-amdgpu@{llvm_amdgpu_version}"]

            llvm_amdgpu["exclude_from_cache"] = cache_exclude
            compilers["llvm-amdgpu"] = llvm_amdgpu

        self.compilers = compilers

    # The path of the default configuration for the target system/cluster
    @property
    def system_config_path(self):
        return self._system_path

    @system_config_path.setter
    def system_config_path(self, path):
        system_path = pathlib.Path(path)
        if not system_path.is_absolute():
            system_path = pathlib.Path.cwd() / system_path

        if not system_path.is_dir():
            raise FileNotFoundError(f"The system configuration path '{system_path}' does not exist")

        self._system_path = system_path

    @property
    def mount(self):
        return pathlib.Path(self.config["store"])

    @property
    def compiler_files(self):
        files = {}

        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(self.template_path),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        makefile_template = env.get_template("Makefile.compilers")
        push_to_cache = self.mirror is not None
        files["makefile"] = makefile_template.render(
            compilers=self.compilers,
            push_to_cache=push_to_cache,
            spack_version=self.spack_version,
        )

        files["config"] = {}
        for compiler, config in self.compilers.items():
            spack_yaml_template = env.get_template(f"compilers.{compiler}.spack.yaml")
            files["config"][compiler] = {}
            # compilers/<compiler>/spack.yaml
            files["config"][compiler]["spack.yaml"] = spack_yaml_template.render(config=config)
            # compilers/gcc/packages.yaml
            if compiler == "gcc":
                files["config"][compiler]["packages.yaml"] = self.packages["gcc"]

        return files

    @property
    def environment_files(self):
        files = {}

        jenv = jinja2.Environment(
            loader=jinja2.FileSystemLoader(self.template_path),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        jenv.filters["py2yaml"] = schema.py2yaml

        makefile_template = jenv.get_template("Makefile.environments")
        push_to_cache = self.mirror is not None
        files["makefile"] = makefile_template.render(
            environments=self.environments,
            push_to_cache=push_to_cache,
            spack_version=self.spack_version,
        )

        files["config"] = {}
        for env, config in self.environments.items():
            spack_yaml_template = jenv.get_template("environments.spack.yaml")
            # generate the spack.yaml file
            files["config"][env] = spack_yaml_template.render(config=config, name=env, store=self.mount)

        return files
