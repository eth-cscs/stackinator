import copy
import pathlib

import jinja2
import yaml

from . import cache, root_logger, schema, spack_util


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

        # check the version of the recipe
        if self.config["version"] != 2:
            rversion = self.config["version"]
            if rversion == 1:
                self._logger.error(
                    "\nThe recipe is an old version 1 recipe for Spack v0.23 and earlier.\n"
                    "This version of Stackinator supports Spack 1.0, and has deprecated support for Spack v0.23.\n"
                    "Use version 5 of stackinator, which can be accessed via the releases/v5 branch:\n"
                    "    git switch releases/v5\n\n"
                    "If this recipe is to be used with Spack 1.0, then please add the field 'version: 2' to\n"
                    "config.yaml in your recipe.\n\n"
                    "For more information: https://eth-cscs.github.io/stackinator/recipes/#configuration\n"
                )
                raise RuntimeError("incompatible uenv recipe version")
            else:
                self._logger.error(
                    f"\nThe config.yaml file sets an unknown recipe version={rversion}.\n"
                    "This version of Stackinator supports version 2 recipes.\n\n"
                    "For more information: https://eth-cscs.github.io/stackinator/recipes/#configuration\n"
                )
                raise RuntimeError("incompatible uenv recipe version")

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
            raw = yaml.load(fid, Loader=yaml.Loader)
            schema.compilers_validator.validate(raw)
            self.generate_compiler_specs(raw)

        # required environments.yaml file
        environments_path = self.path / "environments.yaml"
        self._logger.debug(f"opening {environments_path}")
        if not environments_path.is_file():
            raise FileNotFoundError(f"The recipe path '{environments_path}' does not contain environments.yaml")

        with environments_path.open() as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            # add a special environment that installs tools required later in the build process.
            # currently we only need squashfs for creating the squashfs file.
            raw["uenv_tools"] = {
                "compiler": ["gcc"],
                "mpi": None,
                "unify": True,
                "deprecated": False,
                "specs": ["squashfs"],
                "views": {},
            }
            schema.environments_validator.validate(raw)
            self.generate_environment_specs(raw)

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
                self.packages = yaml.load(fid, Loader=yaml.Loader)

        self._logger.debug("creating packages")

        # load recipe/packages.yaml -> recipe_packages (if it exists)
        recipe_packages = {}
        recipe_packages_path = self.path / "packages.yaml"
        if recipe_packages_path.is_file():
            with recipe_packages_path.open() as fid:
                raw = yaml.load(fid, Loader=yaml.Loader)
                recipe_packages = raw["packages"]

        # load system/packages.yaml -> system_packages (if it exists)
        system_packages = {}
        system_packages_path = self.system_config_path / "packages.yaml"
        if system_packages_path.is_file():
            # load system yaml
            with system_packages_path.open() as fid:
                raw = yaml.load(fid, Loader=yaml.Loader)
                system_packages = raw["packages"]

        # extract gcc packages from system packages
        # remove gcc from packages afterwards
        if system_packages["gcc"]:
            gcc_packages = {"gcc": system_packages["gcc"]}
            del system_packages["gcc"]
        else:
            raise RuntimeError("The system packages.yaml file does not provide gcc")

        self.packages = {
            # the package definition used in every environment
            "global": {"packages": system_packages | recipe_packages},
            # the package definition used to build gcc (requires system gcc to bootstrap)
            "gcc": {"packages": system_packages | gcc_packages | recipe_packages},
        }

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
            raw = yaml.load(fid, Loader=yaml.Loader)
            schema.config_validator.validate(raw)
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
            view = env["view"]
            if view is not None:
                view_meta[view["name"]] = {
                    "root": view["config"]["root"],
                    "activate": view["config"]["root"] + "/activate.sh",
                    "description": "",  # leave the description empty for now
                }

        return view_meta

    @property
    def modules_yaml(self):
        with self.modules.open() as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            raw["modules"]["default"]["roots"]["tcl"] = (pathlib.Path(self.mount) / "modules").as_posix()
            return yaml.dump(raw)

    # creates the self.environments field that describes the full specifications
    # for all of the environments sets, grouped in environments, from the raw
    # environments.yaml input.
    def generate_environment_specs(self, raw):
        environments = raw

        # enumerate large binary packages that should not be pushed to binary caches
        for _, config in environments.items():
            config["exclude_from_cache"] = ["cuda", "nvhpc", "perl"]

        # check the environment descriptions and amend where features are missing
        for name, config in environments.items():
            if ("specs" not in config) or (config["specs"] is None):
                environments[name]["specs"] = []

            if "mpi" not in config:
                environments[name]["mpi"] = {"spec": None, "gpu": None, "network": {"spec": None}}

            if config["mpi"] is None:
                environments[name]["mpi"] = {"spec": None, "gpu": None, "network": {"spec": ""}}

            elif "network" not in config["mpi"]:
                environments[name]["mpi"]["network"] = {"spec": ""}

        # we have not loaded the system configs yet, so mpi information will be generated
        # during the builder phase. We will validate the mpi information then.

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

        # An awkward hack to work around spack not supporting creating activation
        # scripts for each file system view in an environment: it only generates them
        # for the "default" view.
        # The workaround is to create multiple versions of the same environment, one
        # for each view.
        # TODO: remove when the minimum supported version of spack is v0.21, in which
        # this issue was fixed, see https://github.com/spack/spack/pull/40549
        # we have a `--develop` workaround that uses the current approach of generating
        # a separate environment for each view, with a view named "default", and uses
        # the name default to generated the activation script.
        env_names = set()
        env_name_map = {}
        for name, config in environments.items():
            env_name_map[name] = []
            for view, vc in config["views"].items():
                if view in env_names:
                    raise Exception(f"An environment view with the name '{view}' already exists.")
                # set some default values:
                # vc["link"] = "roots"
                # vc["uenv"]["add_compilers"] = True
                # vc["uenv"]["prefix_paths"] = {}
                if vc is None:
                    vc = {}
                vc.setdefault("link", "roots")
                vc.setdefault("uenv", {})
                vc["uenv"].setdefault("add_compilers", True)
                vc["uenv"].setdefault("prefix_paths", {})
                prefix_string = ",".join(
                    [f"{name}={':'.join(paths)}" for name, paths in vc["uenv"]["prefix_paths"].items()]
                )
                vc["uenv"]["prefix_string"] = prefix_string
                # save a copy of the view configuration
                env_name_map[name].append((view, vc))

        # Iterate over each environment:
        # - creating copies of the env so that there is one copy per view.
        # - configure each view
        for name, views in env_name_map.items():
            numviews = len(env_name_map[name])

            # The configuration of the environment without views
            base = copy.deepcopy(environments[name])

            environments[name]["view"] = None
            for i in range(numviews):
                # pick a name for the environment
                cname = name if i == 0 else name + f"-{i + 1}__"
                if i > 0:
                    environments[cname] = copy.deepcopy(base)

                view_name, view_config = views[i]
                # note: the root path is stored as a string, not as a pathlib.PosixPath
                # to avoid serialisation issues when generating the spack.yaml file for
                # each environment.
                if view_config is None:
                    view_config = {"root": str(self.mount / "env" / view_name)}
                else:
                    view_config["root"] = str(self.mount / "env" / view_name)

                # The "uenv" field is not spack configuration, it is additional information
                # used by stackinator additionally set compiler paths and LD_LIBRARY_PATH
                # Remove it from the view_config that will be passed directly to spack, and pass
                # it separately for configuring the envvars.py helper during the uenv build.
                extra = view_config.pop("uenv")

                environments[cname]["view"] = {"name": view_name, "config": view_config, "extra": extra}

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
                files["config"][compiler]["packages.yaml"] = yaml.dump(self.packages["gcc"])

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
            files["config"][env] = spack_yaml_template.render(config=config, name=env, store=self.mount)

        return files
