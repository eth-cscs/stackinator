import argparse
import os
import os.path
import shutil
import subprocess
import sys

import jinja2
import yaml

tool_prefix = ''

def make_argparser():
    parser = argparse.ArgumentParser(description='Generate a build configuration for a spack stack from a recipe.')
    parser.add_argument('-b', '--build',
            required=True,
            type=str)
    parser.add_argument('-r', '--recipe',
            required=True,
            type=str)
    parser.add_argument('-d', '--debug', action='store_true')
    return parser

def validate_recipe_config(config):
    # TODO: create config error type
    if "cpu" not in config.keys():
        raise FileNotFoundError('config.yaml: missing cpu')
    if config["cpu"] not in ["zen3", "zen2"]:
        raise FileNotFoundError('config.yaml: invalid target cpu architecture "{0}"'.format(config["cpu"]))
    if "gpu" not in config.keys():
        config["gpu"] = "NONE"
    if config["gpu"] not in ["A100", "Mi200", "NONE"]:
        raise FileNotFoundError('config.yaml: invalid target gpu architecture "{0}"'.format(config["gpu"]))
    return config

class Recipe:
    path = ''
    compilers = {}
    config = {}

    def __init__(self, args):
        path = args.recipe
        if not os.path.isabs(path):
            path = os.path.join(os.path.abspath(os.path.curdir), path)
        if not os.path.isdir(path):
            raise FileNotFoundError('The recipe path \'{path}\' does not exist'.format(path=path))
        self.path=path

        compiler_path = os.path.join(path, 'compilers.yaml')
        if not os.path.isfile(compiler_path):
            raise FileNotFoundError('The recipe path \'{path}\' does not contain compilers.yaml'.format(path=compiler_path))
        with open(compiler_path) as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            self.compilers = raw['compilers']

        packages_path = os.path.join(path, 'packages.yaml')
        if not os.path.isfile(packages_path):
            raise FileNotFoundError('The recipe path \'{path}\' does not contain packages.yaml'.format(path=packages_path))
        with open(packages_path) as fid:
            raw = yaml.load(fid, Loader=yaml.Loader)
            self.packages = raw['packages']

        config_path = os.path.join(path, 'config.yaml')
        if not os.path.isfile(config_path):
            raise FileNotFoundError('The recipe path \'{path}\' does not contain compilers.yaml'.format(path=config_path))
        with open(config_path) as fid:
            self.config = validate_recipe_config(yaml.load(fid, Loader=yaml.Loader))


    def generate_compilers(self):
        # TODO tests for validity
        # - requires statements:
        #   - at least one compiler must have no upstream (typically bootstrap/1-gcc)
        #   - each compiler is only allowed to have one upstream requirements
        #   - the requires statements must form a tree (should be fulfilled if the first two are met)

        files = {}

        # generate compilers/Makefile
        requirements=[]
        for compiler, config in self.compilers.items():
            requirement = {'compiler': compiler, 'upstream': False}
            if 'requires' in config:
                # python is icky like this
                R=list(config['requires'].items())[0]
                requirement['upstream'] = {'name': R[0], 'spec': R[1]}
            requirements.append(requirement)

        template_path = os.path.join(tool_prefix, 'templates')
        env = jinja2.Environment(
                loader = jinja2.FileSystemLoader(template_path),
                trim_blocks=True, lstrip_blocks=True)

        makefile_template = env.get_template('Makefile.compilers.jinja2')
        files['makefile'] = makefile_template.render(compilers=self.compilers, requirements=requirements)

        # generate compilers/<compiler>/spack.yaml
        files['config'] = {}
        for compiler, config in self.compilers.items():
            spack_yaml_template = env.get_template('spack.yaml.jinja2')
            files['config'][compiler] = spack_yaml_template.render(config=config)

        return files

    def generate_packages(self):
        files = {}

        template_path = os.path.join(tool_prefix, 'templates')
        jenv = jinja2.Environment(
                loader = jinja2.FileSystemLoader(template_path),
                trim_blocks=True, lstrip_blocks=True)

        print(self.packages)
        makefile_template = jenv.get_template('Makefile.packages.jinja2')
        files['makefile'] = makefile_template.render(compilers=self.compilers, environments=self.packages)
        print(files['makefile'])

        print('------------------------------------------------------------------')
        print(self.packages)
        print('------------------------------------------------------------------')

        files['config'] = {}
        for env, config in self.packages.items():
            spack_yaml_template = jenv.get_template('spack.yaml.packages.jinja2')
            files['config'][env] = spack_yaml_template.render(config=config)
            print(files['config'][env])
            print('------------------------------------------------------------------')

        return files


class Build:
    # The path where the project is to be created
    path = ''

    def __init__(self, args):
        path = args.build
        if not os.path.isabs(path):
            path = os.path.join(os.path.abspath(os.path.curdir), path)
        if os.path.exists(path):
            if not os.path.isdir(path):
                raise IOError('build path is not a directory')
            #if os.listdir(path):
                #raise IOError('build path must be empty if it exists')

        self.path = path

    def generate(self, recipe):
        os.makedirs(self.path, exist_ok=True)
        os.makedirs(os.path.join(self.path, 'store'), exist_ok=True)
        os.makedirs(os.path.join(self.path, 'tmp'), exist_ok=True)

        # check out the version of spack
        spack = recipe.config['spack']
        spack_path = os.path.join(self.path, 'spack')
        # clone the repository if the repos has not already been checked out
        if not os.path.isdir(os.path.join(spack_path, '.git')):
            return_code = subprocess.call(["git", "clone", spack['repo'], spack_path], shell=False)
            if return_code != 0:
                raise RuntimeError('error cloning the repository {0}'.format(spack['repo']))
        return_code = subprocess.call(["git", "-C", spack_path, "checkout", spack['commit']], shell=False)
        if return_code != 0:
            raise RuntimeError('unable to change to the requested commit {0}'.format(spack['commit']))

        template_path = os.path.join(tool_prefix, 'templates')
        env = jinja2.Environment(
                loader = jinja2.FileSystemLoader(template_path),
                trim_blocks=True, lstrip_blocks=True)

        # generate top level makefiles
        make_user_template = env.get_template('make.user.jinja2')
        with open(os.path.join(self.path, 'Make.user'), 'w') as f:
            f.write(make_user_template.render(build_path=self.path, store=recipe.config['store'], verbose=False))
            f.write('\n')
            f.close()

        etc_path = os.path.join(tool_prefix, 'etc')
        for f in ['Makefile', 'Make.inc', 'bwrap-mutable-root.sh']:
            shutil.copy2(os.path.join(etc_path, f), os.path.join(self.path, f))

        # generate the system configuration
        config_path = os.path.join(self.path, 'config')
        os.makedirs(config_path, exist_ok=True)
        system = recipe.config['system']
        system_configs_path = os.path.join(os.path.join(os.path.join(tool_prefix, 'share'), 'cluster-config'), system)
        if not os.path.isdir(system_configs_path):
            raise RuntimeError('the system name {0} does not match any known system configuration'.format(system))

        for f in os.listdir(system_configs_path):
            # construct full file path
            src = os.path.join(system_configs_path, f)
            dst = os.path.join(config_path, f)
            # copy only files
            if os.path.isfile(src):
                shutil.copy(src, dst)

        # generate the makefile and spack.yaml files that describe the compilers
        compilers = recipe.generate_compilers()
        compiler_path = os.path.join(self.path, 'compilers')
        os.makedirs(compiler_path, exist_ok=True)
        with open(os.path.join(compiler_path, 'Makefile'), mode='w') as f:
            f.write(compilers['makefile'])
            f.close()

        for name, yaml in compilers['config'].items():
            compiler_config_path = os.path.join(compiler_path, name)
            os.makedirs(compiler_config_path, exist_ok=True)
            with open(os.path.join(compiler_config_path, 'spack.yaml'), mode='w') as f:
                f.write(yaml)
                f.close()

        # generate the makefile and spack.yaml files that describe the packages
        packages = recipe.generate_packages()
        package_path = os.path.join(self.path, 'packages')
        os.makedirs(package_path, exist_ok=True)
        with open(os.path.join(package_path, 'Makefile'), mode='w') as f:
            f.write(packages['makefile'])
            f.close()


        for name, yaml in packages['config'].items():
            pkg_config_path = os.path.join(package_path, name)
            os.makedirs(pkg_config_path, exist_ok=True)
            with open(os.path.join(pkg_config_path, 'spack.yaml'), mode='w') as f:
                f.write(yaml)
                f.close()

        # generate the makefile that generates the configuration for the spack installation
        make_config_template = env.get_template('Makefile.generate-config.jinja2')
        generate_config_path = os.path.join(self.path, 'generate-config')
        os.makedirs(generate_config_path, exist_ok=True)
        compiler_names=[x for x in recipe.compilers.keys() if x!="bootstrap"]
        with open(os.path.join(generate_config_path, 'Makefile'), 'w') as f:
            f.write(make_config_template.render(build_path=self.path, compilers=compiler_names, verbose=False))
            f.write('\n')
            f.close()

def main(prefix):
    global tool_prefix
    tool_prefix = prefix

    try:
        parser = make_argparser()
        args = parser.parse_args()
        recipe = Recipe(args)
        build = Build(args)
        build.generate(recipe)

        return 0
    except Exception as e:
        print(str(e))
        if args.debug:
            raise
        return 1

