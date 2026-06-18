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

from . import VERSION, root_logger, spack_util

_REPO_YAML = """\
repo:
  namespace: {namespace}
  api: v2.0
"""


def install(src, dst, *, ignore=None, symlinks=False):
    """Call shutil.copytree or shutil.copy2, then apply chmod a+rX to dst."""

    def apply_permissions_recursive(directory):
        def set_permissions(path):
            mode = os.stat(path).st_mode
            new_mode = mode | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
            if stat.S_ISDIR(mode) or mode & (stat.S_IXUSR | stat.S_IXGRP):
                new_mode |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            os.chmod(path, new_mode)

        set_permissions(directory)
        for dirpath, dirnames, filenames in os.walk(directory):
            for dirname in dirnames:
                set_permissions(os.path.join(dirpath, dirname))
            for filename in filenames:
                set_permissions(os.path.join(dirpath, filename))

    if stat.S_ISDIR(os.stat(src).st_mode):
        shutil.copytree(src, dst, ignore=ignore, symlinks=symlinks)
    else:
        shutil.copy2(src, dst, follow_symlinks=symlinks)
    apply_permissions_recursive(dst)


class Builder:
    def __init__(self, args):
        self._logger = root_logger
        path = pathlib.Path(args.build)
        if not path.is_absolute():
            path = pathlib.Path.cwd() / path

        if path.exists():
            if not path.is_dir():
                raise IOError("build path is not a directory")

        parts = path.parts
        if len(parts) == 1:
            raise IOError("build path can't be root '/'")
        if parts[1] == "tmp":
            raise IOError("build path can't be in '/tmp'")
        home_parts = pathlib.Path.home().parts
        if (len(home_parts) <= len(parts)) and (home_parts == parts[: len(home_parts)]):
            raise IOError("build path can't be in '$HOME' or '~'")

        self.path = path
        self.root = pathlib.Path(__file__).parent.resolve()

    @property
    def configuration_meta(self):
        return self._configuration_meta

    @configuration_meta.setter
    def configuration_meta(self, recipe):
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
        meta["mount"] = str(recipe.mount)
        meta["spack"] = recipe.config["spack"]
        self._configuration_meta = meta

    @property
    def environment_meta(self):
        return self._environment_meta

    @environment_meta.setter
    def environment_meta(self, recipe):
        conf = recipe.config
        meta = {}
        meta["name"] = conf["name"]
        meta["description"] = conf["description"]
        meta["views"] = recipe.environment_view_meta
        meta["default-view"] = recipe.default_view
        meta["mount"] = str(recipe.mount)
        modules = None
        if recipe.with_modules:
            modules = {"root": str(recipe.mount / "modules")}
        meta["modules"] = modules
        self._environment_meta = meta

    def generate(self, recipe):
        store_path = self.path / "store" if not recipe.no_bwrap else pathlib.Path(recipe.mount)
        tmp_path = self.path / "tmp"
        config_path = self.path / "config"

        self.path.mkdir(exist_ok=True, parents=True)
        env_path = self.path / "env"
        env_path.mkdir(exist_ok=True)
        store_path.mkdir(exist_ok=True)
        tmp_path.mkdir(exist_ok=True)
        config_path.mkdir(exist_ok=True)

        self.configuration_meta = recipe
        self.environment_meta = recipe

        # Clone spack
        spack = recipe.config["spack"]
        spack_path = self.path / "spack"
        spack_git_commit = self._git_clone("spack", spack["repo"], spack["commit"], spack_path)

        package_repos = recipe.spack_package_repos
        for pkg_repo in package_repos:
            pkg_repo["path"] = self.path / "repos" / pkg_repo["name"]
            pkg_repo["commit"] = self._git_clone(pkg_repo["name"], pkg_repo["url"], pkg_repo["ref"], pkg_repo["path"])

        spack_meta = {
            "url": spack["repo"],
            "ref": spack["commit"],
            "commit": spack_git_commit,
            "packages": package_repos,
        }

        # Jinja environment for templates
        template_path = self.root / "templates"
        jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # --- Write the unified spack.yaml ---
        with (env_path / "spack.yaml").open("w") as f:
            f.write(recipe.spack_yaml)
            f.write("\n")

        # Write the spack mirror config artifacts (mirrors.yaml, bootstrap config,
        # and the relocated gpg keys) into the config scope. These were fully
        # resolved and validated by the recipe, so we just write the bytes. This
        # must precede the Makefile render, which references the gpg key paths.
        self._logger.debug(f"Writing the spack mirror configs to '{config_path}'")
        for dest, content in recipe.mirrors.config_files(config_path).items():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)

        # --- Write Makefile ---
        has_views = any(env_cfg["views"] for env_cfg in recipe.environments.values())
        makefile_template = jinja_env.get_template("Makefile")

        # Extract module types that were configured in recipe.py
        module_types = []
        if recipe.with_modules and recipe.modules:
            roots = recipe.modules.get("modules", {}).get("default", {}).get("roots", {})
            module_types = list(roots.keys())

        with (self.path / "Makefile").open("w") as f:
            f.write(
                makefile_template.render(
                    modules=recipe.with_modules,
                    module_types=module_types,
                    post_install_hook=recipe.post_install_hook,
                    pre_install_hook=recipe.pre_install_hook,
                    spack_meta=spack_meta,
                    environments=recipe.environments,
                    compiler_names=recipe.compiler_names,
                    gpg_keys=recipe.mirrors.gpg_key_paths(config_path),
                    cache=recipe.build_cache_mirror,
                    buildcache_push=recipe.push_to_build_cache,
                    exclude_from_cache=["nvhpc", "cuda", "perl"],
                    has_views=has_views,
                    cleanup=recipe.config["cleanup"],
                    system_gcc=recipe.system_gcc,
                )
            )
            f.write("\n")

        # --- Write Make.user ---
        make_user_template = jinja_env.get_template("Make.user")
        with (self.path / "Make.user").open("w") as f:
            f.write(
                make_user_template.render(
                    build_path=self.path,
                    store=recipe.mount,
                    no_bwrap=recipe.no_bwrap,
                    verbose=False,
                )
            )
            f.write("\n")

        # --- Write the sandbox wrapper (binds baked in, self-labelling) ---
        sandbox_template = jinja_env.get_template("sandbox")
        sandbox_dst = self.path / "sandbox"
        with sandbox_dst.open("w") as f:
            f.write(
                sandbox_template.render(
                    build_path=self.path,
                    store=recipe.mount,
                    no_bwrap=recipe.no_bwrap,
                )
            )
        os.chmod(sandbox_dst, os.stat(sandbox_dst).st_mode | stat.S_IEXEC)

        # --- Copy static files from etc/ ---
        etc_path = self.root / "etc"
        for f_etc in ["Make.inc", "bwrap-mutable-root.sh", "envvars.py", "compiler-config.py"]:
            shutil.copy2(etc_path / f_etc, self.path / f_etc)

        # --- Install hooks if provided ---
        hook_env = {
            "mount": recipe.mount,
            "config": recipe.mount / "config",
            "build": self.path,
            "spack": self.path / "spack",
        }

        for hook_name, hook_src in [
            ("post-install", recipe.post_install_hook),
            ("pre-install", recipe.pre_install_hook),
        ]:
            if hook_src is not None:
                self._logger.debug(f"installing {hook_name} script")
                jinja_recipe_env = jinja2.Environment(loader=jinja2.FileSystemLoader(recipe.path))
                hook_template = jinja_recipe_env.get_template(hook_src.name)
                hook_dst = store_path / f"{hook_name}-hook"
                with hook_dst.open("w") as f:
                    f.write(hook_template.render(env=hook_env, verbose=False))
                    f.write("\n")
                os.chmod(hook_dst, os.stat(hook_dst).st_mode | stat.S_IEXEC)

        # the packages.yaml configuration that will be used when building all environments
        # - the system packages.yaml with gcc removed
        # - plus additional packages provided by the recipe
        with (config_path / "packages.yaml").open("w") as f:
            f.write(yaml.dump(recipe.packages))

        config_yaml = {"config": {"install_tree": {"root": str(recipe.mount)}}}
        with (config_path / "config.yaml").open("w") as f:
            f.write(yaml.dump(config_yaml))

        # Add custom spack package recipes, configured via Spack repos.
        # Build a list of repos with packages to install from system config.
        # Packages in the recipe are prioritised over cluster specific packages.
        # Order of preference from highest to lowest:
        #   3. recipe/repo
        #   2. cluster-config/repos.yaml entries
        #   1. package repos from config.yaml (e.g. spack-packages builtin)
        repos = []

        # look for repos.yaml file in the system configuration
        repo_yaml_path = recipe.system_config_path / "repos.yaml"
        if repo_yaml_path.exists() and repo_yaml_path.is_file():
            with repo_yaml_path.open() as fid:
                raw = yaml.load(fid, Loader=yaml.Loader)
            for rel_path in raw["repos"]:
                repo_path = (recipe.system_config_path / rel_path).resolve()
                if spack_util.is_repo(repo_path):
                    repos.append(repo_path)
                    self._logger.debug(f"adding site spack package repo: {repo_path}")
                else:
                    self._logger.error(f"{repo_path} from {repo_yaml_path} is not a spack package repository")
                    raise RuntimeError("invalid system-provided package repository")

        self._logger.debug(f"full list of system spack package repos: {repos}")

        # Delete the store/repo path, if it already exists.
        # Do this so that incremental builds (though not officially supported) won't break if a repo is updated.
        repos_path = store_path / "repos" / "spack_repo"
        repo_dst = repos_path / "alps"
        if repo_dst.exists():
            shutil.rmtree(repo_dst)
        pkg_dst = repo_dst / "packages"
        pkg_dst.mkdir(mode=0o755, parents=True)

        # create the repository step 2: create the repo.yaml file that
        # configures the alps repo
        with (repo_dst / "repo.yaml").open("w") as f:
            f.write(_REPO_YAML.format(namespace="alps"))

        # If the recipe provides a package repo, install it as a separate
        # "recipe" repo in the store with highest precedence.
        has_recipe_repo = recipe.spack_repo is not None
        if has_recipe_repo:
            recipe_dst = repos_path / "recipe"
            self._logger.debug(f"creating the recipe spack repo in {recipe_dst}")
            if recipe_dst.exists():
                self._logger.debug(f"{recipe_dst} exists ... deleting")
                shutil.rmtree(recipe_dst)

            recipe_pkg_dst = recipe_dst / "packages"
            recipe_pkg_dst.mkdir(mode=0o755, parents=True)

            with (recipe_dst / "repo.yaml").open("w") as f:
                f.write(_REPO_YAML.format(namespace="recipe"))

            packages_path = recipe.spack_repo / "packages"
            for pkg_path in packages_path.iterdir():
                dst = recipe_pkg_dst / pkg_path.name
                if pkg_path.is_dir():
                    self._logger.debug(f"  installing recipe package {pkg_path} to {recipe_pkg_dst}")
                    install(pkg_path, dst)

        repos_yaml_template = jinja_env.get_template("repos.yaml")
        with (config_path / "repos.yaml").open("w") as f:
            repo_path = recipe.mount / "repos" / "spack_repo" / "alps"
            recipe_repo_path = recipe.mount / "repos" / "spack_repo" / "recipe"
            package_repos = [
                {
                    "name": pkg_repo["name"],
                    "path": (recipe.mount / "repos" / "spack_repo" / pkg_repo["name"]).as_posix(),
                }
                for pkg_repo in spack_meta["packages"]
            ]
            f.write(
                repos_yaml_template.render(
                    repo_path=repo_path.as_posix(),
                    package_repos=package_repos,
                    recipe_repo_path=recipe_repo_path.as_posix(),
                    has_recipe_repo=has_recipe_repo,
                    verbose=False,
                )
            )
            f.write("\n")

        # Iterate over the alps and recipe repositories copying their contents
        # to the final repo locations. Because of the order of repos in the
        # repos.yaml config file, recipe packages have precedence.
        for repo_src in repos:
            self._logger.debug(f"installing repo {repo_src}")
            packages_path = repo_src / "packages"
            for pkg_path in packages_path.iterdir():
                dst = pkg_dst / pkg_path.name
                if pkg_path.is_dir() and not dst.exists():
                    self._logger.debug(f"  installing package {pkg_path} to {pkg_dst}")
                    install(pkg_path, dst)
                elif dst.exists():
                    self._logger.debug(f"  NOT installing package {pkg_path}")

        # Copy all package repos defined in config.yaml to their final repo
        # locations.
        for pkg_repo in spack_meta["packages"]:
            clone_path = pkg_repo["path"]
            name = pkg_repo["name"]
            src_path = clone_path / pkg_repo["repo_path"]
            dst_path = store_path / "repos" / "spack_repo" / name
            self._logger.debug(f"copying repo '{name}' from {src_path} to {dst_path}")
            if dst_path.exists():
                self._logger.debug(f"{dst_path} exists ... deleting")
                shutil.rmtree(dst_path)
            install(src_path, dst_path)

        # --- generate-config subdirectory ---
        generate_config_path = self.path / "generate-config"
        generate_config_path.mkdir(exist_ok=True)

        make_config_template = jinja_env.get_template("Makefile.generate-config")
        with (generate_config_path / "Makefile").open("w") as f:
            f.write(
                make_config_template.render(
                    modules=recipe.with_modules,
                    build_path=self.path.as_posix(),
                    compiler_names=recipe.compiler_names,
                )
            )
            f.write("\n")

        # --- modules ---
        if recipe.with_modules:
            modules_path = self.path / "modules"
            modules_path.mkdir(exist_ok=True)
            with (modules_path / "modules.yaml").open("w") as f:
                yaml.dump(recipe.modules, f)

        # --- metadata ---
        meta_path = store_path / "meta"
        meta_path.mkdir(exist_ok=True)

        with (meta_path / "configure.json").open("w") as f:
            f.write(json.dumps(self.configuration_meta, sort_keys=True, indent=2, default=str))
            f.write("\n")

        with (meta_path / "env.json.in").open("w") as f:
            f.write(json.dumps(self.environment_meta, sort_keys=True, indent=2, default=str))
            f.write("\n")

        meta_recipe_path = meta_path / "recipe"
        if meta_recipe_path.exists():
            shutil.rmtree(meta_recipe_path)
        install(recipe.path, meta_recipe_path, ignore=shutil.ignore_patterns(".git"))

        meta_extra_path = meta_path / "extra"
        if meta_extra_path.exists():
            shutil.rmtree(meta_extra_path)
        if recipe.user_extra is not None:
            install(recipe.user_extra, meta_extra_path)
        else:
            meta_extra_path.mkdir()

        # --- debug helper ---
        debug_template = jinja_env.get_template("stack-debug.sh")
        with (self.path / "stack-debug.sh").open("w") as f:
            f.write(
                debug_template.render(
                    mount_path=recipe.mount,
                    build_path=str(self.path),
                    use_bwrap=not recipe.no_bwrap,
                )
            )
            f.write("\n")

    def _git_clone(self, name, repo, commit, path):
        if not (path / ".git").is_dir():
            self._logger.info(f"{name}: clone repository {repo} to {path}")
            capture = subprocess.run(
                ["git", "clone", "--filter=tree:0", repo, path],
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self._logger.debug(capture.stdout.decode("utf-8"))
            if capture.returncode != 0:
                self._logger.error(f"error cloning the repository {repo}")
                capture.check_returncode()
        else:
            self._logger.info(f"{name}: {repo} already cloned to {path}")

        if commit:
            self._logger.info(f"{name}: fetching {commit}")
            capture = subprocess.run(
                ["git", "-C", path, "fetch", "origin", commit],
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self._logger.debug(capture.stdout.decode("utf-8"))
            if capture.returncode != 0:
                capture.check_returncode()

            self._logger.info(f"{name}: checking out {commit}")
            capture = subprocess.run(
                ["git", "-C", path, "checkout", commit],
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self._logger.debug(capture.stdout.decode("utf-8"))
            if capture.returncode != 0:
                capture.check_returncode()
        else:
            self._logger.info(f"{name}: no commit set")

        git_commit = (
            subprocess.run(
                ["git", "-C", path, "rev-parse", "HEAD"],
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            .stdout.strip()
            .decode("utf-8")
        )
        self._logger.info(f"{name}: commit hash is {git_commit}")
        return git_commit
