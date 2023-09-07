import json
import os
import pathlib
import platform
import shutil
import stat
import subprocess
import sys
from datetime import datetime

import jinja2
import yaml

from . import VERSION, cache, root_logger


class Builder:
    def __init__(self, args):
        self._logger = root_logger
        path = pathlib.Path(args.build)
        if not path.is_absolute():
            path = pathlib.Path.cwd() / path

        # check that if the path exists that it is not a file
        if path.exists():
            if not path.is_dir():
                raise IOError("build path is not a directory")

        parts = path.parts

        # the build path can't be root
        if len(parts) == 1:
            raise IOError("build path can't be root '/'")

        # the build path can't be in /tmp because the build step rebinds /tmp.
        if parts[1] == "tmp":
            raise IOError("build path can't be in '/tmp'")

        # the build path can't be in $HOME because the build step rebinds $HOME
        # NOTE that this would be much easier to determine with PosixPath.is_relative_to
        # introduced in Python 3.9.
        home_parts = pathlib.Path.home().parts
        if (len(home_parts) <= len(parts)) and (home_parts == parts[: len(home_parts)]):
            raise IOError("build path can't be in '$HOME' or '~'")
        # if path.is_relative_to(pathlib.Path.home()):
        # raise IOError("build path can't be in '$HOME' or '~'")

        self.path = path
        self.root = pathlib.Path(__file__).parent.resolve()

    @property
    def configuration_meta(self):
        """Meta data about the configuration and build"""
        return self._configuration_meta

    @configuration_meta.setter
    def configuration_meta(self, recipe):
        # generate configuration meta data
        meta = {}
        meta["time"] = datetime.now().strftime("%Y%m%d %H:%M:%S")
        host_data = platform.uname()
        meta["host"] = {
            "machine": host_data.machine,
            "node": host_data.node,
            "processor": host_data.processor,
            "release": host_data.release,
            "system": host_data.system,
            "version": host_data.version,
        }
        meta["cluster"] = os.getenv("CLUSTER_NAME", default="unknown")
        meta["stackinator"] = {
            "version": VERSION,
            "args": sys.argv,
            "python": sys.executable,
        }
        meta["spack"] = recipe.config["spack"]
        self._configuration_meta = meta

    @property
    def environment_meta(self):
        """The meta data file that describes the environments"""
        return self._environment_meta

    @environment_meta.setter
    def environment_meta(self, recipe):
        """
        The output that we want to generate looks like the following,
        Which should correspond directly to the environment_view_meta provided
        by the recipe.

        {
          name: "prgenv-gnu",
          description: "useful programming tools",
          modules: {
              "root": /user-environment/modules,
          },
          views: {
            "default": {
              "root": /user-environment/env/default,
              "activate": /user-environment/env/default/activate.sh,
              "description": "simple devolpment env: compilers, MPI, python, cmake."
            },
            "tools": {
              "root": /user-environment/env/tools,
              "activate": /user-environment/env/tools/activate.sh,
              "description": "handy tools"
            }
          }
        }
        """
        conf = recipe.config
        meta = {}
        meta["name"] = conf["name"]
        meta["description"] = conf["description"]
        meta["views"] = recipe.environment_view_meta
        modules = None
        if conf["modules"]:
            modules = {"root": str(recipe.mount / "modules")}
        meta["modules"] = modules
        self._environment_meta = meta

    def generate(self, recipe):
        # make the paths
        store_path = self.path / "store"
        tmp_path = self.path / "tmp"

        self.path.mkdir(exist_ok=True, parents=True)
        store_path.mkdir(exist_ok=True)
        tmp_path.mkdir(exist_ok=True)

        # check out the version of spack
        spack = recipe.config["spack"]
        spack_path = self.path / "spack"

        # set general build and configuration meta data for the project
        self.configuration_meta = recipe

        # set the environment view meta data
        self.environment_meta = recipe

        # Clone the spack repository if it has not already been checked out
        if not (spack_path / ".git").is_dir():
            self._logger.info(f'spack: clone repository {spack["repo"]}')

            # clone the repository
            capture = subprocess.run(
                ["git", "clone", spack["repo"], spack_path],
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self._logger.debug(capture.stdout.decode("utf-8"))

            if capture.returncode != 0:
                self._logger.debug(f'error cloning the repository {spack["repo"]}')
                capture.check_returncode()

        # Check out a branch or commit if one was specified
        if spack["commit"]:
            self._logger.info(f'spack: checkout branch/commit {spack["commit"]}')
            capture = subprocess.run(
                ["git", "-C", spack_path, "checkout", spack["commit"]],
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self._logger.debug(capture.stdout.decode("utf-8"))

            if capture.returncode != 0:
                self._logger.debug(
                    f'unable to change to the requested commit {spack["commit"]}'
                )
                capture.check_returncode()

        # load the jinja templating environment
        template_path = self.root / "templates"
        jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # generate top level makefiles
        makefile_template = jinja_env.get_template("Makefile")

        with (self.path / "Makefile").open("w") as f:
            f.write(
                makefile_template.render(
                    cache=recipe.mirror,
                    modules=recipe.config["modules"],
                    post_install_hook=recipe.post_install_hook,
                    pre_install_hook=recipe.pre_install_hook,
                    verbose=False,
                )
            )
            f.write("\n")

        make_user_template = jinja_env.get_template("Make.user")
        with (self.path / "Make.user").open("w") as f:
            f.write(
                make_user_template.render(
                    build_path=self.path, store=recipe.mount, verbose=False
                )
            )
            f.write("\n")

        etc_path = self.root / "etc"
        for f_etc in ["Make.inc", "bwrap-mutable-root.sh", "add-compiler-links.py"]:
            shutil.copy2(etc_path / f_etc, self.path / f_etc)

        # used to configure both pre and post install hooks, if they are provided.
        hook_env = {
            "mount": recipe.mount,
            "config": recipe.mount / "config",
            "build": self.path,
            "spack": self.path / "spack",
        }

        # copy post install hook file, if provided
        post_hook = recipe.post_install_hook
        if post_hook is not None:
            self._logger.debug("installing post-install-hook script")
            jinja_recipe_env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(recipe.path)
            )
            post_hook_template = jinja_recipe_env.get_template("post-install")
            post_hook_destination = store_path / "post-install-hook"

            with post_hook_destination.open("w") as f:
                f.write(post_hook_template.render(env=hook_env, verbose=False))
                f.write("\n")

            os.chmod(
                post_hook_destination,
                os.stat(post_hook_destination).st_mode | stat.S_IEXEC,
            )

        # copy pre install hook file, if provided
        pre_hook = recipe.pre_install_hook
        if pre_hook is not None:
            self._logger.debug("installing pre-install-hook script")
            jinja_recipe_env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(recipe.path)
            )
            pre_hook_template = jinja_recipe_env.get_template("pre-install")
            pre_hook_destination = store_path / "pre-install-hook"

            with pre_hook_destination.open("w") as f:
                f.write(pre_hook_template.render(env=hook_env, verbose=False))
                f.write("\n")

            os.chmod(
                pre_hook_destination,
                os.stat(pre_hook_destination).st_mode | stat.S_IEXEC,
            )

        # Generate the system configuration: the compilers, environments, etc.
        # that are defined for the target cluster.
        config_path = self.path / "config"
        config_path.mkdir(exist_ok=True)
        system_config_path = pathlib.Path(recipe.system_config_path)

        # Copy the yaml files to the spack config path
        for f_config in system_config_path.iterdir():
            # print warning if mirrors.yaml is found
            if f_config.name in ["mirrors.yaml"]:
                self._logger.error(
                    "mirrors.yaml have been removed from cluster configurations,"
                    " use the --cache option on stack-config instead."
                )
                raise RuntimeError(
                    "Unsupported mirrors.yaml file in cluster configuration."
                )

            # construct full file path
            src = system_config_path / f_config.name
            dst = config_path / f_config.name
            # copy only files
            if src.is_file():
                shutil.copy(src, dst)

        # generate a mirrors.yaml file if build caches have been configured
        if recipe.mirror:
            dst = config_path / "mirrors.yaml"
            self._logger.debug(f"generate the build cache mirror: {dst}")
            with dst.open("w") as fid:
                fid.write(cache.generate_mirrors_yaml(recipe.mirror))

        # append recipe packages to packages.yaml
        if recipe.packages:
            system_packages = system_config_path / "packages.yaml"
            packages_data = {}
            if system_packages.is_file():
                # load system yaml
                with system_packages.open() as fid:
                    raw = yaml.load(fid, Loader=yaml.Loader)
                    packages_data = raw["packages"]
            packages_data.update(recipe.packages["packages"])
            packages_yaml = yaml.dump({"packages": packages_data})
            packages_path = config_path / "packages.yaml"
            with packages_path.open("w") as fid:
                fid.write(packages_yaml)

        # Configure the CSCS custom spack environments.
        # Step 1: copy the CSCS repo to store_path where, it will be used to
        #         build the stack, and then be part of the upstream provided
        #         to users of the stack.
        repo_src = self.root / "repo"
        repo_dst = store_path / "repo"
        if repo_dst.exists():
            shutil.rmtree(repo_dst)

        shutil.copytree(repo_src, repo_dst)

        # Step 2: Create a repos.yaml file in build_path/config
        repos_yaml_template = jinja_env.get_template("repos.yaml")
        with (config_path / "repos.yaml").open("w") as f:
            repo_path = recipe.mount / "repo"
            f.write(
                repos_yaml_template.render(
                    repo_path=repo_path.as_posix(), verbose=False
                )
            )
            f.write("\n")

        # Add user-defined repo to internal repo
        user_repo_path = recipe.path / "repo"
        if user_repo_path.exists() and user_repo_path.is_dir():
            user_repo_yaml = user_repo_path / "repo.yaml"
            if user_repo_yaml.exists():
                self._logger.warning(f"Found 'repo.yaml' file in {user_repo_path}")
                self._logger.warning(
                    "'repo.yaml' is ignored, packages are added to the 'alps' repo"
                )

            # Copy user-provided recipes into repo
            user_repo_packages = user_repo_path / "packages"
            for user_recipe_dir in user_repo_packages.iterdir():
                if user_recipe_dir.is_dir():  # iterdir() yelds files too
                    shutil.copytree(
                        user_recipe_dir, repo_dst / "packages" / user_recipe_dir.name
                    )

        # Generate the makefile and spack.yaml files that describe the compilers
        compiler_files = recipe.compiler_files
        compiler_path = self.path / "compilers"
        compiler_path.mkdir(exist_ok=True)
        with (compiler_path / "Makefile").open(mode="w") as f:
            f.write(compiler_files["makefile"])

        for name, yml in compiler_files["config"].items():
            compiler_config_path = compiler_path / name
            compiler_config_path.mkdir(exist_ok=True)
            with (compiler_config_path / "spack.yaml").open(mode="w") as f:
                f.write(yml)

        # generate the makefile and spack.yaml files that describe the environments
        environment_files = recipe.environment_files
        environments_path = self.path / "environments"
        os.makedirs(environments_path, exist_ok=True)
        with (environments_path / "Makefile").open(mode="w") as f:
            f.write(environment_files["makefile"])

        for name, yml in environment_files["config"].items():
            env_config_path = environments_path / name
            env_config_path.mkdir(exist_ok=True)
            with (env_config_path / "spack.yaml").open(mode="w") as f:
                f.write(yml)

        # generate the makefile that generates the configuration for the spack
        # installation in the generate-config sub-directory of the build path.
        make_config_template = jinja_env.get_template("Makefile.generate-config")
        generate_config_path = self.path / "generate-config"
        generate_config_path.mkdir(exist_ok=True)

        # write generate-config/Makefile
        all_compilers = [x for x in recipe.compilers.keys()]
        release_compilers = [x for x in all_compilers if x != "bootstrap"]
        with (generate_config_path / "Makefile").open("w") as f:
            f.write(
                make_config_template.render(
                    build_path=self.path.as_posix(),
                    all_compilers=all_compilers,
                    release_compilers=release_compilers,
                    verbose=False,
                )
            )

        # write modules/modules.yaml
        modules_yaml = recipe.modules_yaml
        generate_modules_path = self.path / "modules"
        generate_modules_path.mkdir(exist_ok=True)
        with (generate_modules_path / "modules.yaml").open("w") as f:
            f.write(modules_yaml)

        # write the meta data
        meta_path = self.path / "store/meta"
        meta_path.mkdir(exist_ok=True)
        # write a json file with basic meta data
        with (meta_path / "configure.json").open("w") as f:
            # default serialisation is str to serialise the pathlib.PosixPath
            f.write(
                json.dumps(
                    self.configuration_meta, sort_keys=True, indent=2, default=str
                )
            )
            f.write("\n")

        # write a json file with the environment view meta data
        with (meta_path / "env.json").open("w") as f:
            # default serialisation is str to serialise the pathlib.PosixPath
            f.write(
                json.dumps(self.environment_meta, sort_keys=True, indent=2, default=str)
            )
            f.write("\n")

        # copy the recipe to a recipe subdirectory of the meta path
        meta_recipe_path = meta_path / "recipe"
        meta_recipe_path.mkdir(exist_ok=True)
        if meta_recipe_path.exists():
            shutil.rmtree(meta_recipe_path)
        shutil.copytree(
            recipe.path, meta_recipe_path, ignore=shutil.ignore_patterns(".git")
        )

        # create the meta/extra path and copy recipe meta data if it exists
        meta_extra_path = meta_path / "extra"
        meta_extra_path.mkdir(exist_ok=True)
        if meta_extra_path.exists():
            shutil.rmtree(meta_extra_path)
        if recipe.user_extra is not None:
            self._logger.debug(f"copying extra recipe meta data to {meta_extra_path}")
            shutil.copytree(recipe.user_extra, meta_extra_path)

        # create debug helper script
        debug_script_path = self.path / "stack-debug.sh"
        debug_script_template = jinja_env.get_template("stack-debug.sh")
        with debug_script_path.open("w") as f:
            f.write(
                debug_script_template.render(
                    mount_path=recipe.mount,
                    build_path=str(self.path),
                    verbose=False,
                )
            )
            f.write("\n")
