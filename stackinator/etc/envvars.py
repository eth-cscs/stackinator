#!/usr/bin/python3

import argparse
import json
import os
from enum import Enum
from typing import List, Optional

import yaml


class EnvVarOp(Enum):
    PREPEND = 1
    APPEND = 2
    SET = 3

    def __str__(self):
        return self.name.lower()


class EnvVarKind(Enum):
    SCALAR = 2
    LIST = 2


list_variables = {
    "ACLOCAL_PATH",
    "CMAKE_PREFIX_PATH",
    "CPATH",
    "LD_LIBRARY_PATH",
    "LIBRARY_PATH",
    "MANPATH",
    "MODULEPATH",
    "PATH",
    "PKG_CONFIG_PATH",
    "PYTHONPATH",
}


class EnvVarError(Exception):
    """Exception raised when there is an error with environment variable manipulation."""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return self.message


def is_env_value_list(v):
    return isinstance(v, list) and all(isinstance(item, str) for item in v)


class ListEnvVarUpdate:
    def __init__(self, value: List[str], op: EnvVarOp):
        # clean up paths as they are inserted
        self._value = [os.path.normpath(p) for p in value]
        self._op = op

    @property
    def op(self):
        return self._op

    @property
    def value(self):
        return self._value

    def set_op(self, op: EnvVarOp):
        self._op = op

    # remove all paths that have root as common root
    def remove_root(self, root: str):
        root = os.path.normpath(root)
        self._value = [p for p in self._value if root != os.path.commonprefix([root, p])]

    def __repr__(self):
        return f"envvar.ListEnvVarUpdate({self.value}, {self.op})"

    def __str__(self):
        return f"({self.value}, {self.op})"


class EnvVar:
    def __init__(self, name: str):
        self._name = name

    @property
    def name(self):
        return self._name


class ListEnvVar(EnvVar):
    def __init__(self, name: str, value: List[str], op: EnvVarOp):
        super().__init__(name)

        self._updates = [ListEnvVarUpdate(value, op)]

    def update(self, value: List[str], op: EnvVarOp):
        self._updates.append(ListEnvVarUpdate(value, op))

    def remove_root(self, root: str):
        for i in range(len(self._updates)):
            self._updates[i].remove_root(root)

    @property
    def updates(self):
        return self._updates

    def concat(self, other: "ListEnvVar"):
        self._updates += other.updates

    def prepend(self, other: "ListEnvVar"):
        self._updates = other.updates + self._updates

    def make_dirty(self):
        if len(self._updates) > 0:
            self._updates[0].set_op(EnvVarOp.PREPEND)

    @property
    def paths(self):
        paths = []
        for u in self._updates:
            paths += u.value
        return paths

    # Given the current value, return the value that should be set
    # current is None implies that the variable is not set
    #
    # dirty allows for not overriding the current value of the variable.
    def get_value(self, current: Optional[str], dirty: bool = False):
        v = current

        # if the variable is currently not set, first initialise it as empty.
        if v is None:
            if len(self._updates) == 0:
                return None
            v = ""

        first = True
        for update in self._updates:
            joined = ":".join(update.value)
            if first and dirty and update.op == EnvVarOp.SET:
                op = EnvVarOp.PREPEND
            else:
                op = update.op

            if v == "" or op == EnvVarOp.SET:
                v = joined
            elif op == EnvVarOp.APPEND:
                v = ":".join([v, joined])
            elif op == EnvVarOp.PREPEND:
                v = ":".join([joined, v])
            else:
                raise EnvVarError(f"Internal error: implement the operation {update.op}")

            first = False
            # strip any leading/trailing ":"
            v = v.strip(":")

        return v

    def __repr__(self):
        return f'envvars.ListEnvVar("{self.name}", {self._updates})'

    def __str__(self):
        return f"(\"{self.name}\": [{','.join([str(u) for u in self._updates])}])"


class ScalarEnvVar(EnvVar):
    def __init__(self, name: str, value: Optional[str]):
        super().__init__(name)
        self._value = value

    @property
    def value(self):
        return self._value

    @property
    def is_null(self):
        return self.value is None

    def update(self, value: Optional[str]):
        self._value = value

    def get_value(self, value: Optional[str]):
        if value is not None:
            return value
        return self._value

    def __repr__(self):
        return f'envvars.ScalarEnvVar("{self.name}", "{self.value}")'

    def __str__(self):
        return f'("{self.name}": "{self.value}")'


class Env:
    def __init__(self):
        self._vars = {}

    def apply(self, var: EnvVar):
        self._vars[var.name] = var


# returns true if the environment variable with name is a list variable,
# e.g. PATH, LD_LIBRARY_PATH, PKG_CONFIG_PATH, etc.
def is_list_var(name: str) -> bool:
    return name in list_variables


class EnvVarSet:
    """
    A set of environment variable updates.

    The values need to be applied before they are valid.
    """

    def __init__(self):
        self._lists = {}
        self._scalars = {}
        # toggles whether post export commands will be generated
        self._generate_post = True

    @property
    def lists(self):
        return self._lists

    def clear(self):
        self._lists = {}
        self._scalars = {}

    @property
    def scalars(self):
        return self._scalars

    def make_dirty(self):
        for name in self._lists:
            self._lists[name].make_dirty()

    def remove_root(self, root: str):
        for name in self._lists:
            self._lists[name].remove_root(root)

    def set_scalar(self, name: str, value: str):
        self._scalars[name] = ScalarEnvVar(name, value)

    def set_list(self, name: str, value: List[str], op: EnvVarOp, concat: bool = True):
        var = ListEnvVar(name, value, op)
        if var.name in self._lists.keys():
            if concat:
                self._lists[var.name].concat(var)
            else:
                self._lists[var.name].prepend(var)
        else:
            self._lists[var.name] = var

    def __repr__(self):
        return f'envvars.EnvVarSet("{self.lists}", "{self.scalars}")'

    def __str__(self):
        s = "EnvVarSet:\n"
        s += "  scalars:\n"
        for _, v in self.scalars.items():
            s += f"    {v.name}: {v.value}\n"
        s += "  lists:\n"
        for _, v in self.lists.items():
            s += f"    {v.name}:\n"
            for u in v.updates:
                s += f"      {u.op}: {':'.join(u.value)}\n"
        return s

    # Update the environment variables using the values in another EnvVarSet.
    # This operation is used when environment variables are sourced from more
    # than one location, e.g. multiple activation scripts.
    def update(self, other: "EnvVarSet"):
        for name, var in other.scalars.items():
            self.set_scalar(name, var.value)
        for name, var in other.lists.items():
            if name in self.lists.keys():
                self.lists[name].concat(var)
            else:
                self.lists[name] = var

    # Generate the commands that set and unset the environment variables.
    # Returns a dictionary with two fields:
    #   "pre": the list of commands to be executed before the command
    #   "post": the list of commands to be executed to revert the environment
    #
    # The "post" list is optional, and should not be used for commands that
    # update the environment like "uenv view" and "uenv modules use", instead
    # it should be used for commands that should not alter the calling environment,
    # like "uenv run" and "uenv start".
    #
    # The dirty flag will preserve the state of variables like PATH, LD_LIBRARY_PATH, etc.
    def export(self, dirty=False):
        pre = []
        post = []

        for name, var in self.scalars.items():
            # get the value of the environment variable
            current = os.getenv(name)
            new = var.get_value(current)

            if new is None:
                pre.append(f"unset {name}")
            else:
                pre.append(f"export {name}={new}")

            if self._generate_post:
                if current is None:
                    post.append(f"unset {name}")
                else:
                    post.append(f"export {name}={current}")

        for name, var in self.lists.items():
            # get the value of the environment variable
            current = os.getenv(name)
            new = var.get_value(current, dirty)

            if new is None:
                pre.append(f"unset {name}")
            else:
                pre.append(f"export {name}={new}")

            if self._generate_post:
                if current is None:
                    post.append(f"unset {name}")
                else:
                    post.append(f"export {name}={current}")

        return {"pre": pre, "post": post}

    def as_dict(self) -> dict:
        # create a dictionary with the information formatted for JSON
        d = {"list": {}, "scalar": {}}

        for name, var in self.lists.items():
            ops = []
            for u in var.updates:
                op = "set" if u.op == EnvVarOp.SET else ("prepend" if u.op == EnvVarOp.PREPEND else "append")
                ops.append({"op": op, "value": u.value})

            d["list"][name] = ops

        for name, var in self.scalars.items():
            d["scalar"][name] = var.value

        return d

    # returns a string that represents the environment variable modifications
    # in json format
    # {
    #    "list": {
    #        "PATH": [
    #                {"op": "set", "value": "/user-environment/bin"},
    #                {"op": "prepend", "value": "/user-environment/env/default/bin"}
    #            ],
    #        "LD_LIBRARY_PATH": [
    #                {"op": "prepend", "value": "/user-environment/env/default/lib"}
    #                {"op": "prepend", "value": "/user-environment/env/default/lib64"}
    #            ]
    #    },
    #    "scalar": {
    #        "CUDA_HOME": "/user-environment/env/default",
    #        "MPIF90": "/user-environment/env/default/bin/mpif90"
    #    }
    # }
    def as_json(self) -> str:
        return json.dumps(self.as_dict(), separators=(",", ":"))

    def set_post(self, value: bool):
        self._generate_post = value


def read_activation_script(filename: str, env: Optional[EnvVarSet] = None) -> EnvVarSet:
    if env is None:
        env = EnvVarSet()

    with open(filename) as fid:
        for line in fid:
            ls = line.strip().rstrip(";")
            # skip empty lines and comments
            if (len(ls) == 0) or (ls[0] == "#"):
                continue
            # split on the first whitespace
            # this splits lines of the form
            # export Y
            # where Y is an arbitray string into ['export', 'Y']
            fields = ls.split(maxsplit=1)

            # handle lines of the form 'export Y'
            if len(fields) > 1 and fields[0] == "export":
                fields = fields[1].split("=", maxsplit=1)
                # get the name of the environment variable
                name = fields[0]

                # ignore SPACK environment variables: setting these will interfere with downstream
                # user spack configuration.
                if name.startswith("SPACK_"):
                    continue

                # if there was only one field, there was no = sign, so pass
                if len(fields) < 2:
                    continue

                # rhs the value that is assigned to the environment variable
                rhs = fields[1]
                if name in list_variables:
                    fields = [f for f in rhs.split(":") if len(f.strip()) > 0]
                    # look for $name as one of the fields (only works for append or prepend)

                    if len(fields) == 0:
                        env.set_list(name, fields, EnvVarOp.SET)
                    elif fields[0] == f"${name}":
                        env.set_list(name, fields[1:], EnvVarOp.APPEND)
                    elif fields[-1] == f"${name}":
                        env.set_list(name, fields[:-1], EnvVarOp.PREPEND)
                    else:
                        env.set_list(name, fields, EnvVarOp.SET)
                else:
                    env.set_scalar(name, rhs)

    return env


def view_impl(args):
    print(
        f"parsing view {args.root}\n  compilers {args.compilers}\n  prefix_paths '{args.prefix_paths}'\n  \
        build_path '{args.build_path}'"
    )

    if not os.path.isdir(args.root):
        print(f"error - environment root path {args.root} does not exist")
        exit(1)

    root_path = args.root
    activate_path = root_path + "/activate.sh"
    if not os.path.isfile(activate_path):
        print(f"error - activation script {activate_path} does not exist")
        exit(1)

    envvars = read_activation_script(activate_path)

    # force all prefix path style variables (list vars) to use PREPEND the first operation.
    envvars.make_dirty()
    # remove all paths that refer to the build directory of the uenv
    envvars.remove_root(args.build_path)

    if args.compilers is not None:
        if not os.path.isfile(args.compilers):
            print(f"error - compiler yaml file {args.compilers} does not exist")
            exit(1)

        with open(args.compilers, "r") as file:
            data = yaml.safe_load(file)
        compilers = [c["compiler"] for c in data["compilers"]]

        for c in compilers:
            source_paths = list(set([os.path.abspath(v) for _, v in c["paths"].items() if v is not None]))
            target_paths = [os.path.join(os.path.join(root_path, 'bin'), os.path.basename(f)) for f in source_paths]
            for src, dst in zip(source_paths, target_paths):
                print(f'creating compiler symlink: {src} -> {dst}')
                if os.path.exists(dst):
                    print(f'  first removing {dst}')
                    os.remove(dst)
                os.symlink(src, dst)

    if args.prefix_paths:
        # get the root path of the env
        print(f"prefix_paths: searching in {root_path}")

        for p in args.prefix_paths.split(","):
            name, value = p.split("=")
            paths = []
            for path in [os.path.normpath(p) for p in value.split(":")]:
                test_path = f"{root_path}/{path}"
                if os.path.isdir(test_path):
                    paths.append(test_path)

            print(f"{name}:")
            for p in paths:
                print(f"  {p}")

            if len(paths) > 0:
                if name in envvars.lists:
                    ld_paths = envvars.lists[name].paths
                    final_paths = [p for p in paths if p not in ld_paths]
                    envvars.set_list(name, final_paths, EnvVarOp.PREPEND)
                else:
                    envvars.set_list(name, paths, EnvVarOp.PREPEND)

    json_path = os.path.join(root_path, "env.json")
    print(f"writing JSON data to {json_path}")
    envvar_dict = {"version": 1, "values": envvars.as_dict()}
    with open(json_path, "w") as fid:
        json.dump(envvar_dict, fid)
        fid.write("\n")


def meta_impl(args):
    # verify that the paths exist
    if not os.path.exists(args.mount):
        print(f"error - uenv mount '{args.mount}' does not exist.")
        exit(1)

    # parse the uenv meta data from file
    meta_in_path = os.path.normpath(f"{args.mount}/meta/env.json.in")
    meta_path = os.path.normpath(f"{args.mount}/meta/env.json")
    print(f"loading meta data to update: {meta_in_path}")
    with open(meta_in_path) as fid:
        meta = json.load(fid)

    for name, data in meta["views"].items():
        env_root = data["root"]

        # read the json view data from file
        json_path = os.path.join(env_root, "env.json")
        print(f"reading view {name} data rom {json_path}")

        if not os.path.exists(json_path):
            print(f"error - meta data file '{json_path}' does not exist.")
            exit(1)

        with open(json_path, "r") as fid:
            envvar_dict = json.load(fid)

        # update the global meta data to include the environment variable state
        meta["views"][name]["env"] = envvar_dict
        meta["views"][name]["type"] = "spack-view"

    # process spack and modules
    if args.modules:
        module_path = f"{args.mount}/modules"
        meta["views"]["modules"] = {
            "activate": "/dev/null",
            "description": "activate modules",
            "root": module_path,
            "env": {
                "version": 1,
                "type": "augment",
                "values": {"list": {"MODULEPATH": [{"op": "prepend", "value": [module_path]}]}, "scalar": {}},
            },
        }

    if args.spack is not None:
        spack_url, spack_ref, spack_commit = args.spack.split(",")
        spack_path = f"{args.mount}/config".replace("//", "/")
        meta["views"]["spack"] = {
            "activate": "/dev/null",
            "description": "configure spack upstream",
            "root": spack_path,
            "env": {
                "version": 1,
                "type": "augment",
                "values": {
                    "list": {},
                    "scalar": {
                        "UENV_SPACK_CONFIG_PATH": spack_path,
                        "UENV_SPACK_REF": spack_ref,
                        "UENV_SPACK_COMMIT": spack_commit,
                        "UENV_SPACK_URL": spack_url,
                    },
                },
            },
        }

    # update the uenv meta data file with the new env. variable description
    with open(meta_path, "w") as fid:
        # write updated meta data
        json.dump(meta, fid)
        fid.write("\n")
    print(f"wrote the uenv meta data {meta_path}")


if __name__ == "__main__":
    # parse CLI arguments
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    view_parser = subparsers.add_parser(
        "view", formatter_class=argparse.RawDescriptionHelpFormatter, help="generate env.json for a view"
    )
    view_parser.add_argument("root", help="root path of the view", type=str)
    view_parser.add_argument("build_path", help="build_path", type=str)
    view_parser.add_argument(
        "--prefix_paths", help="a list of relative prefix path searchs of the form X=y:z,Y=p:q", default="", type=str
    )
    # only add compilers if this argument is passed
    view_parser.add_argument("--compilers", help="path of the compilers.yaml file", type=str, default=None)

    uenv_parser = subparsers.add_parser(
        "uenv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="generate meta.json meta data file for a uenv.",
    )
    uenv_parser.add_argument("mount", help="mount point of the image", type=str)
    uenv_parser.add_argument("--modules", help="configure a module view", action="store_true")
    uenv_parser.add_argument(
        "--spack",
        help='configure a spack view. Format is "spack_url,git_ref,git_commit"',
        type=str,
        default=None,
    )

    args = parser.parse_args()

    if args.command == "uenv":
        print("!!! running meta")
        meta_impl(args)
    elif args.command == "view":
        print("!!! running view")
        view_impl(args)
