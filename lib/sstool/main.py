import argparse
import os
import os.path
import sys
import yaml
import jinja2

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

class Recipe:
    path = ''
    compilers = {}

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
            raw_compilers = yaml.load(fid, Loader=yaml.Loader)
            self.compilers = raw_compilers['compilers']

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

        env = jinja2.Environment(
                loader = jinja2.FileSystemLoader('./templates'),
                trim_blocks=True,
                lstrip_blocks=True)

        make_template = env.get_template('Makefile.compilers.jinja2')

        files['makefile'] = make_template.render(compilers=self.compilers, requirements=requirements)

        # generate compilers/<compiler>/spack.yaml

        files['config'] = {}
        for compiler, config in self.compilers.items():
            make_template = env.get_template('spack.yaml.jinja2')
            files['config'][compiler] = make_template.render(config=config)

        return files


class Build:
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

        # generate the makefile and spack.yaml files that describe the compilers
        compilers = recipe.generate_compilers()
        compiler_path = os.path.join(self.path, 'compilers')
        os.makedirs(compiler_path, exist_ok=True)
        with open(os.path.join(compiler_path, 'Makefile'), mode='w') as f:
            f.write(compilers['makefile'])
            f.close()

        for name, yaml in compilers['config'].items():
            config_path = os.path.join(compiler_path, name)
            os.makedirs(config_path, exist_ok=True)
            with open(os.path.join(config_path, 'spack.yaml'), mode='w') as f:
                f.write(yaml)
                f.close()

def main(argv=None):
    try:
        parser = make_argparser()
        args = parser.parse_args(argv)
        recipe = Recipe(args)
        build = Build(args)
        build.generate(recipe)

        return 0
    except Exception as e:
        print(str(e))
        if args.debug:
            raise
        return 1

