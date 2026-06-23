import copy
import pathlib
import re

import jinja2
import yaml

from . import root_logger, schema, spack_util, mirror
from .etc.envvars import EnvVarSet


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
            raw = yaml.load(fid, Loader=yaml.Loader)
            schema.CompilersValidator.validate(raw)
            self.generate_compiler_specs(raw)

        # optional modules.yaml file
        self.modules = None
        modules_path = self.path / "modules.yaml"
        self._logger.debug(f"opening {modules_path}")
        if modules_path.is_file():
            with modules_path.open() as fid:
                self.modules = yaml.load(fid, Loader=yaml.Loader)
                schema.ModulesValidator.validate(self.modules)

                # Note:
                # modules root should match MODULEPATH set by envvars and used by uenv view "modules"
                # so we enforce that the user does not override it in modules.yaml

                # Spack supports these module types (as of Spack 1.0+)
                VALID_MODULE_TYPES = {"tcl", "lmod"}

                # Update the root path for each module type that the user configured
                # This respects the user's choice of tcl, lmod, or both
                defaults = self.modules["modules"].setdefault("default", {})
                roots = defaults.setdefault("roots", {})

                # Determine which module types to configure
                # Priority: 1) explicit roots:, 2) enable: list, 3) default to tcl
                if not roots:
                    # No explicit roots configured, check enable: list
                    enabled = defaults.get("enable", [])
                    if enabled:
                        # Use the enabled module types
                        module_types = enabled
                    else:
                        # No enable list either, default to tcl for backward compatibility
                        module_types = ["tcl"]
                else:
                    # Use explicitly configured roots
                    module_types = list(roots.keys())

                # Set the root path for each module type
                for module_type in module_types:
                    if module_type not in VALID_MODULE_TYPES:
                        raise ValueError(
                            f"Invalid module type '{module_type}' in modules.yaml. "
                            f"Supported types: {', '.join(sorted(VALID_MODULE_TYPES))}"
                        )
                    roots[module_type] = (self.mount / "modules").as_posix()

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
            with system_packages_path.open() as fid:
                raw = yaml.load(fid, Loader=yaml.Loader)
                system_packages = raw["packages"]

        if "gcc" not in system_packages:
            raise RuntimeError("The system packages.yaml file does not provide gcc")

        # load the optional network.yaml from system config
        network_path = self.system_config_path / "network.yaml"
        network_packages = {}
        mpi_templates = {}
        if network_path.is_file():
            self._logger.debug(f"opening {network_path}")
            with network_path.open() as fid:
                raw = yaml.load(fid, Loader=yaml.Loader)
                if "packages" in raw:
                    network_packages = raw["packages"]
                if "mpi" in raw:
                    mpi_templates = raw["mpi"]
        self.mpi_templates = mpi_templates

        # note that the order that package sets are specified in is significant.
        # arguments to the right have higher precedence.
        #
        # build_packages: system + network + recipe packages.
        # - system gcc is included here because needed to build the software
        # global_packages: system + network + recipe packages.
        # - system gcc is only included if building with system gcc
        build_packages = system_packages | network_packages | recipe_packages
        install_packages = system_packages | network_packages | recipe_packages
        if not self.use_system_gcc:
            del install_packages["gcc"]

        self.packages = {"build": {"packages": build_packages}, "install": {"packages": install_packages}}

        # required environments.yaml file
        environments_path = self.path / "environments.yaml"
        self._logger.debug(f"opening {environments_path}")
        if not environments_path.is_file():
            raise FileNotFoundError(f"The recipe path '{environments_path}' does not contain environments.yaml")

        with environments_path.open() as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            schema.EnvironmentsValidator.validate(raw)
            self._check_environments_v3(raw)
            self.generate_environment_specs(raw)

        # check that the default view exists (if one has been set)
        self._default_view = self.config["default-view"]
        if self._default_view is not None:
            available_views = [view["name"] for env in self.environments.values() for view in env["views"]]
            if self.with_modules:
                available_views.append("modules")
            available_views.append("spack")
            if self._default_view not in available_views:
                raise RuntimeError(
                    f"The default-view '{self._default_view}' is not the name of a view defined in environments.yaml"
                )

        # determine the version of spack being used: it is inferred (best effort)
        # from the spack commit in config.yaml, defaulting to the latest supported
        # version when it cannot be determined. This must precede the mirror
        # configuration, which gates the concretizer cache on the spack version.
        self.spack_version = self.find_spack_version(args.develop)

        # resolve the mirror configuration provided with --mirror. --cache is the
        # legacy path.
        self._logger.debug("Configuring mirrors.")
        self.mirrors = mirror.Mirrors(
            self.system_config_path,
            self.mount,
            self.spack_version,
            pathlib.Path(args.mirror) if args.mirror else None,
            pathlib.Path(args.cache) if args.cache else None,
        )

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

    def _check_environments_v3(self, raw):
        """Warn about fields that are ignored in v3 recipes."""
        for name, config in raw.items():
            if config and config.get("packages"):
                self._logger.warning(
                    f"environment '{name}': the 'packages' field is ignored in v3 recipes. "
                    "Add external packages to the recipe's packages.yaml instead."
                )

    # Returns:
    #   Path: if the recipe contains a spack package repository
    #   None: if there is the recipe contains no repo
    @property
    def spack_repo(self):
        repo_path = self.path / "repo"
        if spack_util.is_repo(repo_path):
            return repo_path
        return None

    _RESERVED_REPO_NAMES = {"alps", "recipe"}

    @property
    def spack_package_repos(self):
        packages = self.config["spack"]["packages"]
        if isinstance(packages.get("repo"), str):
            return [
                {
                    "name": "builtin",
                    "url": packages["repo"],
                    "ref": packages.get("commit"),
                    "repo_path": packages.get("path", "repos/spack_repo/builtin"),
                }
            ]
        repos = [
            {
                "name": name,
                "url": val["repo"],
                "ref": val.get("commit"),
                "repo_path": val.get("path", f"repos/spack_repo/{name}"),
            }
            for name, val in packages.items()
        ]
        for repo in repos:
            name = repo["name"]
            if name in self._RESERVED_REPO_NAMES:
                raise RuntimeError(
                    f"The package repo name '{name}' is reserved for stackinator internal use. "
                    f"Reserved names are: {self._RESERVED_REPO_NAMES}. "
                    "Choose a different name in config.yaml:spack:packages."
                )
        return repos

    # Returns:
    #   Path: if the recipe specified a build cache mirror
    #   None: if no build cache mirror is used
    @property
    def build_cache_mirror(self):
        return self.mirrors.build_cache_mirror

    # Returns:
    #   str:  the build cache mirror name to push built packages to
    #   None: if there is no build cache, or it is read-only (no signing key)
    @property
    def push_to_build_cache(self):
        return self.mirrors.push_to_build_cache

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
            schema.ConfigValidator.validate(raw)
            self._config = raw

    @property
    def with_modules(self) -> bool:
        return self.modules is not None

    # Make a best-effort determination of the "major.minor" version of spack being
    # used, inferred from the spack commit in config.yaml. This is only a hint: the
    # commit can be an arbitrary branch/tag/sha, so when the version cannot be pinned
    # we default to the latest supported version ("1.1"). Returns a "major.minor"
    # string (e.g. "1.0", "1.1").
    def find_spack_version(self, develop):
        # the latest supported version, used when the version cannot be determined
        # (an explicit --develop, the default branch, or an unrecognised commit).
        default = "1.1"

        if develop:
            return default

        commit = self.config["spack"]["commit"]
        if commit is None or commit in ("develop", "main"):
            return default

        # match a release branch/tag (releases/v1.0, v1.1, v1.1.2) or a bare "1.0",
        # and extract the major.minor version.
        match = re.search(r"v?(\d+)\.(\d+)(?:\.\d+)?", commit)
        if match:
            return f"{match.group(1)}.{match.group(2)}"

        return default

    @property
    def default_view(self):
        return self._default_view

    @property
    def environment_view_meta(self):
        # generate the view meta data that is presented in the squashfs image meta data
        view_meta = {}
        for _, env in self.environments.items():
            for view in env["views"]:
                try:
                    # recipe authors can substitute the name of the view, the mount
                    # and view path into environment variables using '$@key@' where
                    # key is one of view_name, mount and view_path.
                    substitutions = {
                        "view_name": str(view["name"]),
                        "mount": str(self.mount),
                        "view_path": str(view["config"]["root"]),
                    }
                    env_vars = EnvVarSet.from_envvars(view["extra"]["env_vars"], substitutions)
                except Exception as err:
                    raise RuntimeError(f'In view "{view["name"]}": {err}')

                view_meta[view["name"]] = {
                    "root": view["config"]["root"],
                    "description": "",
                    "recipe_variables": env_vars.as_dict(),
                }

        return view_meta

    @property
    def compiler_names(self):
        """Names of the compiler packages installed in this recipe (excludes system gcc)."""
        return [name for name, c in self.compilers.items() if not c.get("system", False)]

    # creates the self.environments field that describes the full specifications
    # for all of the environments sets, grouped in environments, from the raw
    # environments.yaml input.
    def generate_environment_specs(self, raw):
        environments = raw

        for _, config in environments.items():
            config["exclude_from_cache"] = ["cuda", "nvhpc", "perl"]

        for name, config in environments.items():
            if ("specs" not in config) or (config["specs"] is None):
                environments[name]["specs"] = []

        # Resolve MPI specs from the network field
        for name, config in environments.items():
            environments[name]["mpi"] = None

            if config["network"]:
                specs = []

                if config["network"]["mpi"] is not None:
                    spec = config["network"]["mpi"].strip()
                    match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*)", spec)
                    if match:
                        mpi_name = match.group(1)
                        supported_mpis = list(self.mpi_templates.keys())
                        if mpi_name not in supported_mpis:
                            raise Exception(f"{mpi_name} is not a supported MPI: try one of {supported_mpis}.")
                    else:
                        raise Exception(f"{spec} is not a valid MPI spec")

                    specs.append(spec)

                    if config["network"]["specs"]:
                        specs += config["network"]["specs"]
                    elif self.mpi_templates[mpi_name]["specs"]:
                        specs += self.mpi_templates[mpi_name]["specs"]

                    environments[name]["mpi"] = mpi_name
                    environments[name]["specs"] += specs

        # Auto-generate a prefer constraint that pins the default compiler.
        # For built compilers, include the version to distinguish from system externals.
        # For system gcc, omit the version (there is only one gcc available).
        for name, config in environments.items():
            if config["prefer"] is None:
                compiler_key = config["compiler"][0]
                # spack uses a different name for the intel oneapi compilers
                # than the package that installs them.
                compiler_name = "oneapi" if compiler_key == "intel-oneapi-compilers" else compiler_key
                compiler_version = self.compilers[compiler_key].get("version")
                versioned = f"{compiler_name}@{compiler_version}" if compiler_version else compiler_name
                config["prefer"] = [
                    f"%[when=%c] c={versioned} %[when=%cxx] cxx={versioned} %[when=%fortran] fortran={versioned}"
                ]

        # Compute spec group needs: only compilers with actual (non-system) spec groups.
        for name, config in environments.items():
            config["needs"] = [c for c in config["compiler"] if not self.compilers.get(c, {}).get("system", False)]

        # Build view metadata
        env_names = set()
        for name, config in environments.items():
            views = []
            for view_name, vc in config["views"].items():
                if view_name in env_names:
                    raise Exception(f"A view named '{view_name}' is defined more than once.")
                env_names.add(view_name)
                view_config = copy.deepcopy(vc)
                # set some default values:
                # view_config["link"] = "roots"
                # view_config["uenv"]["add_compilers"] = True
                # view_config["uenv"]["prefix_paths"] = {}
                # view_config["uenv"]["env_vars"] = {"set": [], "unset": [], "prepend_path": [], "append_path": []}
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
                # note: root is stored as a string (not pathlib.PosixPath) to avoid
                # serialisation issues when the config is written to spack.yaml.
                view_config["root"] = str(self.mount / "env" / view_name)

                # The "uenv" field is stackinator-specific metadata (compiler paths,
                # env-var rules) — not a spack view config field. Pop it before
                # passing view_config to spack; it travels separately as "extra" and
                # is consumed by envvars.py during the view-generation step.
                extra = view_config.pop("uenv")
                views.append({"name": view_name, "config": view_config, "extra": extra})

            config["views"] = views

        self.environments = environments

    # creates the self.compilers field that describes the full specifications
    # for all of the compilers from the raw compilers.yaml input
    def generate_compiler_specs(self, raw):
        compilers = {}

        gcc_version = raw["gcc"]["version"]
        if gcc_version == "system":
            compilers["gcc"] = {"system": True}
        else:
            compilers["gcc"] = {"specs": [f"gcc@{gcc_version} +bootstrap"], "version": gcc_version}

        for name, spec_template in [
            ("nvhpc", "nvhpc@{version} ~mpi~blas~lapack"),
            ("llvm", "llvm@{version} +clang ~gold"),
            ("llvm-amdgpu", "llvm-amdgpu@{version}"),
            ("intel-oneapi-compilers", "intel-oneapi-compilers@{version}"),
        ]:
            if raw.get(name) is not None:
                version = raw[name]["version"]
                compilers[name] = {"specs": [spec_template.format(version=version)], "version": version}

        self.compilers = compilers

        # will the uenv use the system gcc instead of bootstrapping gcc
        self.use_system_gcc = gcc_version == "system"

    @property
    def system_gcc(self):
        return self.compilers.get("gcc", {}).get("system", False)

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
    def spack_yaml(self):
        """Render the unified spack.yaml for this recipe."""
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(self.template_path),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        env.filters["py2yaml"] = schema.py2yaml

        has_views = any(env_cfg["views"] for env_cfg in self.environments.values())

        template = env.get_template("spack.yaml")
        return template.render(
            compilers=self.compilers,
            environments=self.environments,
            store=self.mount,
            has_views=has_views,
            system_gcc=self.system_gcc,
        )

    @property
    def upstream_config(self):
        return {"upstreams": {"system": {"install_tree": self.mount.as_posix()}}}
