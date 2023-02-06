import argparse
import hashlib
import logging
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import time

import jinja2
import yaml

import stackinator.schema

# The logger, initalised with logging.getLogger
logger = None

# A unique name for the logfile
logfile = ''

def generate_logfile_name(name=''):
    idstr = f'{time.localtime()}{os.getpid}{platform.uname()}'
    return f'log{name}_{hashlib.md5(idstr.encode("utf-8")).hexdigest()}'

def configure_logging():
    # create logger
    logger = logging.getLogger('spack-stack-tool')
    logger.setLevel(logging.DEBUG)

    # create stdout handler and set level to info
    ch = logging.StreamHandler(stream=sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(ch)

    # create log file handler and set level to debug
    fh = logging.FileHandler(logfile) #, mode='w')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter('%(asctime)s : %(levelname)-7s : %(message)s'))
    logger.addHandler(fh)

    return logger

def log_header(args):
    logger.info('Spack Stack Tool')
    logger.info(f'  recipe path: {args.recipe}')
    logger.info(f'  build path : {args.build}')

def make_argparser():
    parser = argparse.ArgumentParser(
        description=('Generate a build configuration for a spack stack from '
                     'a recipe.')
    )
    parser.add_argument('-b', '--build', required=True, type=str)
    parser.add_argument('-r', '--recipe', required=True, type=str)
    parser.add_argument('-d', '--debug', action='store_true')
    return parser

class Mirror:
    def __init__(self, config, source):
        if config:
            enabled = config.get('enable', True)
            key = config.get('key', None)
            self._source = None if not enabled else source
            self._key  = key
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
        "cray-mpich-binary":  (None, None),
        "mpich":  ("4.1", "device=ch4 netmod=ofi +slurm"),
        "mvapich2": (
            "3.0a", 
            "+xpmem fabrics=ch4ofi ch4_max_vcis=4 process_managers=slurm"
        )
    }

    def __init__(self, args):
        logger.debug('Generating recipe')
        path = pathlib.Path(args.recipe)
        if not path.is_absolute():
            path = pathlib.Path.cwd() / path

        if not path.is_dir:
            raise FileNotFoundError(f"The recipe path '{path}' does not exist")

        self.path = path
        self.root = prefix = pathlib.Path(__file__).parent.parent.resolve()

        # required compilers.yaml file
        compiler_path = path / 'compilers.yaml'
        logger.debug(f'opening {compiler_path}')
        if not compiler_path.is_file():
            raise FileNotFoundError(f"The recipe path '{compiler_path}' does "
                                    f"not contain compilers.yaml")

        with compiler_path.open() as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            if 'compilers' in raw:
                logger.warning(f"{compiler_path} uses deprecated 'compilers:' "
                               f"header. This will be an error in future releases.")
                raw = raw['compilers']
            stackinator.schema.compilers_validator.validate(raw)
            self.generate_compiler_specs(raw)

        # required environments.yaml file
        environments_path = path / 'environments.yaml'
        logger.debug(f'opening {environments_path}')
        if not environments_path.is_file():
            raise FileNotFoundError(f"The recipe path '{environments_path}' does "
                                    f" not contain environments.yaml")

        with environments_path.open() as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            self.generate_environment_specs(raw['environments'])

        # required config.yaml file
        config_path = path / 'config.yaml'
        logger.debug(f'opening {config_path}')
        if not config_path.is_file():
            raise FileNotFoundError(f"The recipe path '{config_path}' does "
                                    f"not contain compilers.yaml")

        with config_path.open() as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            stackinator.schema.config_validator.validate(raw)
            self.config = raw

        # optional modules.yaml file
        modules_path = path / 'modules.yaml'
        logger.debug(f'opening {modules_path}')
        if not modules_path.is_file():
            modules_path = (pathlib.Path(args.build) / 
                'spack/etc/spack/defaults/modules.yaml')
            logger.debug(
                f'no modules.yaml provided - using the {modules_path}')

        self.modules = modules_path

        # optional packages.yaml file
        packages_path = path / 'packages.yaml'
        logger.debug(f'opening {packages_path}')
        self.packages = None
        if packages_path.is_file():
            with packages_path.open() as fid:
                self.packages = yaml.load(fid, Loader=yaml.Loader)

        # Select location of the mirrors.yaml file to use.
        # Look first in the recipe path, then in the system configuration path.
        mirrors_path = path / 'mirrors.yaml'
        mirrors_source = mirrors_path if mirrors_path.is_file() else None
        if mirrors_source == None:
            mirrors_path = self.configs_path / 'mirrors.yaml'
            mirrors_source = mirrors_path if mirrors_path.is_file() else None

        self._mirror = Mirror(config=self.config['mirror'],
                              source=mirrors_source)

    @property
    def mirror(self):
        return self._mirror

    def generate_modules(self):
        with self.modules.open() as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            raw['modules']['default']['roots']['tcl'] = (
                pathlib.Path(self.config['store']) / 'modules').as_posix()
            return yaml.dump(raw)

    # creates the self.environments field that describes the full specifications
    # for all of the environments sets, grouped in environments, from the raw
    # environments.yaml input.
    def generate_environment_specs(self, raw):
        environments = raw

        # check the environment descriptions and ammend where features are missing
        for name, config in environments.items():
            if ("specs" not in config) or (config["specs"] == None):
                environments[name]["specs"] = []

            if ("mpi" not in config):
                environments[name]["mpi"] = {"spec": None, "gpu": None}

        for name, config in environments.items():
            mpi = config["mpi"]
            mpi_spec = mpi["spec"]
            mpi_gpu = mpi["gpu"]
            if mpi_spec:
                try:
                    mpi_impl, mpi_ver = mpi_spec.strip().split(
                        sep='@', maxsplit=1)
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

                    if mpi_gpu and mpi_impl != 'cray-mpich-binary':
                        spec = f"{spec} cuda_arch=80"

                    environments[name]["specs"].append(spec)
                else:
                    # TODO: Create a custom exception type
                    raise Exception(f'Unsupported mpi: {mpi_impl}')

        self.environments = environments


    # creates the self.compilers field that describes the full specifications
    # for all of teh compilers from the raw compilers.yaml input
    def generate_compiler_specs(self, raw):
        compilers = {}

        bootstrap = {}
        bootstrap["packages"]= {
            "external": ["perl", "m4", "autoconf", "automake", "libtool", 
                         "gawk", "python", "texinfo", "gawk"],
            "variants": {
                "gcc": "[build_type=Release ~bootstrap +strip]",
                "mpc": "[libs=static]",
                "gmp": "[libs=static]",
                "mpfr": "[libs=static]",
                "zstd": "[libs=static]",
                "zlib": "[~shared]"
            }
        }
        bootstrap_spec = raw["bootstrap"]["spec"]
        bootstrap["specs"] = [f"{bootstrap_spec} languages=c,c++",
                              f"squashfs default_compression=zstd"]
        compilers["bootstrap"] = bootstrap

        gcc = {}
        gcc["packages"] = {
            "external": ["perl", "m4", "autoconf", "automake", "libtool",
                         "gawk", "python", "texinfo", "gawk"],
            "variants": {
                "gcc": "[build_type=Release +profiled +strip]",
                "mpc": "[libs=static]",
                "gmp": "[libs=static]",
                "mpfr": "[libs=static]",
                "zstd": "[libs=static]",
                "zlib": "[~shared]"
            }
        }
        gcc["specs"] = raw["gcc"]["specs"]
        gcc["requires"] = bootstrap_spec
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
                        f"{spec} +clang targets=x86 ~gold ^ninja@kitware")

            llvm["requires"] = raw["llvm"]["requires"]
            compilers["llvm"] = llvm

        self.compilers = compilers

    # The path of the default configuration for the target system/cluster
    @property
    def configs_path(self):
        system = self.config['system']
        return self.root / 'share' / 'cluster-config' / system

    # Boolean flag that indicates whether the recipe is configured to use 
    # a binary cache.
    def generate_compilers(self):
        files = {}

        template_path = self.root / 'templates'
        env = jinja2.Environment(
            loader = jinja2.FileSystemLoader(template_path),
            trim_blocks=True, lstrip_blocks=True)

        makefile_template = env.get_template('Makefile.compilers')
        push_to_cache = self.mirror.source and self.mirror.key
        files['makefile'] = makefile_template.render(
            compilers=self.compilers,
            push_to_cache=push_to_cache)

        # generate compilers/<compiler>/spack.yaml
        files['config'] = {}
        for compiler, config in self.compilers.items():
            spack_yaml_template = env.get_template(
                f'compilers.{compiler}.spack.yaml')
            files['config'][compiler] = spack_yaml_template.render(
                config=config)

        return files

    def generate_environments(self):
        files = {}

        template_path = self.root / 'templates'
        jenv = jinja2.Environment(
            loader = jinja2.FileSystemLoader(template_path),
            trim_blocks=True, lstrip_blocks=True)

        makefile_template = jenv.get_template('Makefile.environments')
        push_to_cache = self.mirror.source and self.mirror.key
        files['makefile'] = makefile_template.render(
            environments=self.environments,
            push_to_cache=push_to_cache)

        files['config'] = {}
        for env, config in self.environments.items():
            spack_yaml_template = jenv.get_template('environments.spack.yaml')
            files['config'][env] = spack_yaml_template.render(config=config)

        return files

class Build:
    def __init__(self, args):
        path = pathlib.Path(args.build)
        if not path.is_absolute():
            path = pathlib.Path.cwd() / path

        if path.exists():
            if not path.is_dir():
                raise IOError('build path is not a directory')

        self.path = path
        self.root = prefix = pathlib.Path(__file__).parent.parent.resolve()

    def generate(self, recipe):
        # make the paths
        store_path = self.path / 'store'
        tmp_path = self.path / 'tmp'

        self.path.mkdir(exist_ok=True, parents=True)
        store_path.mkdir(exist_ok=True)
        tmp_path.mkdir(exist_ok=True)

        # check out the version of spack
        spack = recipe.config['spack']
        spack_path = self.path / 'spack'

        # Clone the spack repository if it has not already been checked out
        if not (spack_path / '.git').is_dir():
            logger.info(f'spack: clone repository {spack["repo"]}')

            # clone the repository
            capture = subprocess.run(
                ["git", "clone", spack['repo'], spack_path],
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT)
            logger.debug(capture.stdout.decode('utf-8'))

            if capture.returncode != 0:
                logger.debug(f'error cloning the repository {spack["repo"]}')
                capture.check_returncode()

        # Check out a branch or commit if one was specified
        if spack['commit']:
            logger.info(f'spack: checkout branch/commit {spack["commit"]}')
            capture = subprocess.run(
                ["git", "-C", spack_path, "checkout", spack['commit']],
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT)
            logger.debug(capture.stdout.decode('utf-8'))

            if capture.returncode != 0:
                logger.debug(
                    f'unable to change to the requested commit {spack["commit"]}')
                capture.check_returncode()

        # load the jinja templating environment
        template_path = self.root / 'templates'
        env = jinja2.Environment(
            loader = jinja2.FileSystemLoader(template_path),
            trim_blocks=True, lstrip_blocks=True)

        # generate top level makefiles
        makefile_template = env.get_template('Makefile')
        with (self.path / 'Makefile').open('w') as f:
            cache = {'key': recipe.mirror.key, 'enabled': recipe.mirror.source}
            f.write(makefile_template.render(
                cache=cache, modules=recipe.config['modules'], verbose=False))
            f.write('\n')

        make_user_template = env.get_template('Make.user')
        with (self.path / 'Make.user').open('w') as f:
            f.write(make_user_template.render(
                build_path=self.path, store=recipe.config['store'],
                verbose=False))
            f.write('\n')

        etc_path = self.root / 'etc'
        for f in ['Make.inc', 'bwrap-mutable-root.sh']:
            shutil.copy2(etc_path / f, self.path / f)

        # Generate the system configuration: the compilers, environments,
        # mirrors etc that are defined for the target cluster.
        config_path = self.path / 'config'
        config_path.mkdir(exist_ok=True)
        system_configs_path = pathlib.Path(recipe.configs_path)

        # Copy the yaml files to the spack config path
        for f in system_configs_path.iterdir():
            # skip copying mirrors.yaml - this is done in the next step only if
            # mirrors have been enabled and the recipe did not provide a mirror
            # configuration
            if f.name in ['mirrors.yaml']:
                continue

            # construct full file path
            src = system_configs_path / f.name
            dst = config_path / f.name
            # copy only files
            if src.is_file():
                shutil.copy(src, dst)

        # copy the optional mirrors file
        if recipe.mirror.source:
            dst = config_path / 'mirrors.yaml'
            shutil.copy(recipe.mirror.source, dst)

        # append recipe packages to packages.yaml
        if recipe.packages:
            system_packages = system_configs_path / 'packages.yaml'
            packages_data = {}
            if system_packages.is_file():
                # load system yaml
                with system_packages.open() as fid:
                    raw = yaml.load(fid, Loader=yaml.Loader)
                    packages_data = raw['packages']
            packages_data.update(recipe.packages['packages'])
            packages_yaml = yaml.dump({'packages': packages_data})
            packages_path = config_path / 'packages.yaml'
            with packages_path.open("w") as fid:
                fid.write(packages_yaml)

        # Configure the CSCS custom spack environments.
        # Step 1: copy the CSCS repo to store_path where, it will be used to
        #         build the stack, and then be part of the upstream provided
        #         to users of the stack.
        repo_src = self.root / 'repo'
        repo_dst = store_path / 'repo'
        if repo_dst.exists():
            shutil.rmtree(repo_dst)

        shutil.copytree(repo_src, repo_dst)

        # Step 2: Create a repos.yaml file in build_path/config
        repos_yaml_template = env.get_template('repos.yaml')
        with (config_path / 'repos.yaml').open('w') as f:
            repo_path = pathlib.Path(recipe.config['store']) / 'repo'
            f.write(repos_yaml_template.render(
                repo_path=repo_path.as_posix(),verbose=False))
            f.write('\n')

        # Generate the makefile and spack.yaml files that describe the compilers
        compilers = recipe.generate_compilers()
        compiler_path = self.path / 'compilers'
        compiler_path.mkdir(exist_ok=True)
        with (compiler_path / 'Makefile').open(mode='w') as f:
            f.write(compilers['makefile'])

        for name, yml in compilers['config'].items():
            compiler_config_path = compiler_path / name
            compiler_config_path.mkdir(exist_ok=True)
            with (compiler_config_path / 'spack.yaml').open(mode='w') as f:
                f.write(yml)

        # generate the makefile and spack.yaml files that describe the environments
        environments = recipe.generate_environments()
        environments_path = self.path / 'environments'
        os.makedirs(environments_path, exist_ok=True)
        with (environments_path / 'Makefile').open(mode='w') as f:
            f.write(environments['makefile'])

        for name, yml in environments['config'].items():
            env_config_path = environments_path / name
            env_config_path.mkdir(exist_ok=True)
            with (env_config_path / 'spack.yaml').open(mode='w') as f:
                f.write(yml)

        # generate the makefile that generates the configuration for the spack
        # installation
        make_config_template = env.get_template('Makefile.generate-config')
        generate_config_path = self.path / 'generate-config'
        generate_config_path.mkdir(exist_ok=True)

        # write the Makefile
        all_compilers=[x for x in recipe.compilers.keys()]
        release_compilers=[x for x in all_compilers if x != "bootstrap"]
        with (generate_config_path / 'Makefile').open('w') as f:
            f.write(make_config_template.render(
                build_path=self.path.as_posix(),
                all_compilers=all_compilers,
                release_compilers=release_compilers,
                verbose=False))

        # write the modules.yaml file
        modules_yaml=recipe.generate_modules()
        generate_modules_path = self.path / 'modules'
        generate_modules_path.mkdir(exist_ok=True)
        with (generate_modules_path / 'modules.yaml').open('w') as f:
            f.write(modules_yaml)

def main():
    global logfile
    logfile = generate_logfile_name('_config')

    global logger
    logger = configure_logging()

    try:
        parser = make_argparser()
        args = parser.parse_args()
        logger.debug(f'Command line arguments: {args}')
        log_header(args)

        recipe = Recipe(args)
        build = Build(args)

        build.generate(recipe)

        logger.info('\nConfiguration finished, run the following to build '
                    'the environment:\n')
        logger.info(f'cd {build.path}')
        logger.info('env --ignore-environment PATH=/usr/bin:/bin:`pwd`'
                    '/spack/bin make store.squashfs -j32')
        return 0
    except Exception as e:
        logger.exception(e)
        logger.info(f'see {logfile} for more information')
        return 1
