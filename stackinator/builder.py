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

from . import VERSION, cache, root_logger, spack_util


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

        self.path.mkdir(exist_ok=True, parents=True)
        env_path = self.path / "env"
        env_path.mkdir(exist_ok=True)
        store_path.mkdir(exist_ok=True)
        tmp_path.mkdir(exist_ok=True)

        self.configuration_meta = recipe
        self.environment_meta = recipe

        # Clone spack
        spack = recipe.config["spack"]
        spack_path = self.path / "spack"
        spack_git_commit = self._git_clone("spack", spack["repo"], spack["commit"], spack_path)

        # Clone spack-packages
        spack_packages = spack["packages"]
        spack_packages_path = self.path / "spack-packages"
        spack_packages_git_commit = self._git_clone(
            "spack-packages",
            spack_packages["repo"],
            spack_packages["commit"],
            spack_packages_path,
        )

        spack_meta = {
            "url": spack["repo"],
            "ref": spack["commit"],
            "commit": spack_git_commit,
            "packages_url": spack_packages["repo"],
            "packages_ref": spack_packages["commit"],
            "packages_commit": spack_packages_git_commit,
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

        # --- Write Makefile ---
        has_views = any(env_cfg["views"] for env_cfg in recipe.environments.values())
        makefile_template = jinja_env.get_template("Makefile")
        with (self.path / "Makefile").open("w") as f:
            f.write(
                makefile_template.render(
                    cache=recipe.mirror,
                    push_to_cache=recipe.mirror is not None,
                    modules=recipe.with_modules,
                    post_install_hook=recipe.post_install_hook,
                    pre_install_hook=recipe.pre_install_hook,
                    spack_meta=spack_meta,
                    environments=recipe.environments,
                    compiler_names=recipe.compiler_names,
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

        # --- Build the consolidated 'alps' spack package repo ---
        # Precedence (highest first): recipe/repo > cluster repos.yaml entries > spack builtin
        repos = []
        if recipe.spack_repo is not None:
            self._logger.debug(f"adding recipe spack package repo: {recipe.spack_repo}")
            repos.append(recipe.spack_repo)

        repo_yaml_path = recipe.system_config_path / "repos.yaml"
        if repo_yaml_path.exists():
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

        repos_path = store_path / "repos" / "spack_repo"
        repo_dst = repos_path / "alps"
        if repo_dst.exists():
            shutil.rmtree(repo_dst)
        pkg_dst = repo_dst / "packages"
        pkg_dst.mkdir(mode=0o755, parents=True)

        with (repo_dst / "repo.yaml").open("w") as f:
            f.write("repo:\n  namespace: alps\n  api: v2.0\n")

        # config/ is the SPACK_SYSTEM_CONFIG_PATH scope: all files here are loaded
        # automatically by every spack command, with or without -e.
        config_path = self.path / "config"
        config_path.mkdir(exist_ok=True)

        with (config_path / "packages.yaml").open("w") as f:
            f.write(yaml.dump(recipe.packages))

        # Force the legacy ("old") installer: the new spack 1.2 installer drives a
        # live TUI via selectors/pipes/non-blocking fds that fails with EBADF under
        # the non-interactive `make` build on older Cray/SLES stacks (system Python
        # 3.6). The TUI is pointless for a batch build in any case.
        config_yaml = {"config": {"install_tree": {"root": str(recipe.mount)}, "installer": "old"}}
        with (config_path / "config.yaml").open("w") as f:
            f.write(yaml.dump(config_yaml))

        repos_yaml_template = jinja_env.get_template("repos.yaml")
        with (config_path / "repos.yaml").open("w") as f:
            repo_path = recipe.mount / "repos" / "spack_repo" / "alps"
            builtin_repo_path = recipe.mount / "repos" / "spack_repo" / "builtin"
            f.write(
                repos_yaml_template.render(
                    repo_path=repo_path.as_posix(), builtin_repo_path=builtin_repo_path.as_posix()
                )
            )
            f.write("\n")

        if recipe.mirror:
            with (config_path / "mirrors.yaml").open("w") as fid:
                fid.write(cache.generate_mirrors_yaml(recipe.mirror))

        # Copy package definitions into the alps repo (recipe > site > nothing)
        for repo_src in repos:
            for pkg_path in (repo_src / "packages").iterdir():
                dst = pkg_dst / pkg_path.name
                if pkg_path.is_dir() and not dst.exists():
                    install(pkg_path, dst)

        # Copy builtin repo from spack-packages
        spack_builtin_src = spack_packages_path / "repos" / "spack_repo" / "builtin"
        spack_builtin_dst = store_path / "repos" / "spack_repo" / "builtin"
        if spack_builtin_dst.exists():
            shutil.rmtree(spack_builtin_dst)
        install(spack_builtin_src, spack_builtin_dst)

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
