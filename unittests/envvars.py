#!/usr/bin/python3

import argparse
from enum import Enum
import json
import os
from typing import Optional, List

class EnvVarOp (Enum):
    PREPEND=1
    APPEND=2
    SET=3

    def __str__(self):
        return self.name.lower()

class EnvVarKind (Enum):
    SCALAR=2
    LIST=2

list_variables = {
        "ACLOCAL_PATH",
        "CMAKE_PREFIX_PATH",
        "CPATH",
        "LD_LIBRARY_PATH",
        "LIBRARY_PATH",
        "MANPATH",
        "PATH",
        "PKG_CONFIG_PATH",
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

class ListEnvVarUpdate():
    def __init__(self, value: List[str], op: EnvVarOp):
        # strip white space from each entry
        self._value = [v.strip() for v in value]
        self._op = op

    @property
    def op(self):
        return self._op

    @property
    def value(self):
        return self._value

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

    def update(self, value: List[str], op:EnvVarOp):
        self._updates.append(ListEnvVarUpdate(value, op))

    @property
    def updates(self):
        return self._updates

    def concat(self, other: 'ListEnvVar'):
        self._updates += other.updates

    # Given the current value, return the value that should be set
    # current is None implies that the variable is not set
    #
    # dirty allows for not overriding the current value of the variable.
    def get_value(self, current: Optional[str], dirty: bool=False):
        v = current

        # if the variable is currently not set, first initialise it as empty.
        if v is None:
            if len(self._updates)==0:
                return None
            v = ""

        first = True
        for update in self._updates:
            joined = ":".join(update.value)
            if first and dirty and update.op==EnvVarOp.SET:
                op = EnvVarOp.PREPEND
            else:
                op = update.op

            if v == "" or op==EnvVarOp.SET:
                v = joined
            elif op==EnvVarOp.APPEND:
                v = ":".join([v, joined])
            elif op==EnvVarOp.PREPEND:
                v = ":".join([joined, v])
            else:
                raise EnvVarError(f"Internal error: implement the operation {update.op}");

            first = False
            # strip any leading/trailing ":"
            v = v.strip(':')

        return v

    def __repr__(self):
        return f"envvars.ListEnvVar(\"{self.name}\", {self._updates})"

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
        return f"envvars.ScalarEnvVar(\"{self.name}\", \"{self.value}\")"

    def __str__(self):
        return f"(\"{self.name}\": \"{self.value}\")"

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

    def set_scalar(self, name: str, value: str):
        self._scalars[name] = ScalarEnvVar(name, value)

    def set_list(self, name: str, value: List[str], op: EnvVarOp):
        var = ListEnvVar(name, value, op)
        if var.name in self._lists.keys():
            old = self._lists[var.name]
            self._lists[var.name].concat(var)
        else:
            self._lists[var.name] = var

    def __repr__(self):
        return f"envvars.EnvVarSet(\"{self.lists}\", \"{self.scalars}\")"

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
    def update(self, other: 'EnvVarSet'):
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
                op = "set" if u.op == EnvVarOp.SET else ("prepend" if u.op==EnvVarOp.PREPEND else "append")
                ops.append({"op": op, "value": u.value})

            d["list"][name] = ops

        for name, var in self.scalars.items():
            d["scalar"][name] = var.value

        return d

    # returns a string that represents the environment variable modifications
    # in json format
    #{
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
    #}
    def as_json(self) -> str:
        return json.dumps(self.as_dict(), separators=(',', ':'))

    def set_post(self, value: bool):
        self._generate_post = value

def read_activation_script(filename: str, env: Optional[EnvVarSet]=None) -> EnvVarSet:
    if env is None:
        env = EnvVarSet()

    with open(filename) as fid:
        for line in fid:
            l = line.strip().rstrip(";")
            # skip empty lines and comments
            if (len(l)==0) or (l[0]=='#'):
                continue
            # split on the first whitespace
            # this splits lines of the form
            # export Y
            # where Y is an arbitray string into ['export', 'Y']
            fields = l.split(maxsplit=1)

            # handle lines of the form 'export Y'
            if len(fields)>1 and fields[0]=='export':
                fields = fields[1].split('=', maxsplit=1)
                # get the name of the environment variable
                name = fields[0]

                # if there was only one field, there was no = sign, so pass
                if len(fields)<2:
                    continue
                # rhs the value that is assigned to the environment variable
                rhs = fields[1]
                if name in list_variables:
                    fields = [f for f in rhs.split(":") if len(f.strip())>0]
                    # look for $name as one of the fields (only works for append or prepend)

                    if len(fields)==0:
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

def impl1():
    # parse CLI arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("script", help="Path to the activate script to parse",
                        type=str)
    parser.add_argument("json", help="Path to where the json file should be ouput",
                        type=str)
    parser.add_argument("meta", help="path to the meta",
                        type=str)
    parser.add_argument("view", help="the name of the view",
                        type=str)
    args = parser.parse_args()

    # verify that the paths exist
    if not os.path.exists(args.script):
        print(f"error - activation script '{args.script}' does not exist.")
        exit(2)
    if not os.path.exists(args.meta):
        print(f"error - uenv meta data file '{args.meta}' does not exist.")
        exit(2)

    # parse the activation script for its environment variable changes
    envvars = read_activation_script(args.script)

    # write the environment variable update to a json file
    print(f"writing environment variable information to json: {args.json}")
    with open(args.json, "w") as fid:
        fid.write(envvars.as_json())
        fid.write("\n")

    # parse the uenv meta data from file
    print(f"loading meta data to update: {args.meta}")
    with open(args.meta) as fid:
        meta = json.load(fid)

    # TODO: handle the case where there is no matching view description
    meta["views"][args.view]["json"] = { "version": 1, "values": envvars.as_dict() }
    meta["views"][args.view]["type"] = "spack-view"

    # update the uenv meta data file with the new env. variable description
    with open(args.meta, "w") as fid:
        # write updated meta data
        json.dump(meta, fid)

def impl2():
    # parse CLI arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("mount",    help="mount point of the image",type=str)
    parser.add_argument("--modules", help="configure a module view", action="store_true")
    parser.add_argument("--spack",  help="configure a spack view. Format is \"spack_url,git_commit\"",  type=str, default=None)
    args = parser.parse_args()

    # verify that the paths exist
    if not os.path.exists(args.mount):
        print(f"error - uenv mount '{args.mount}' does not exist.")
        exit(2)

    # parse the uenv meta data from file
    meta_path = f"{args.mount}/meta/env.json"
    print(f"loading meta data to update: {meta_path}")
    with open(meta_path) as fid:
        meta = json.load(fid)

    for name, data in meta["views"].items():
        env_root = data["root"]
        script_path = data["activate"]
        json_path = os.path.join(env_root, "env.json")

        # parse the activation script for its environment variable changes
        envvars = read_activation_script(script_path)
        envvar_dict = { "version": 1, "values": envvars.as_dict() }

        # write the environment variable update to a json file
        print(f"writing environment variable information to json: {json_path}")
        with open(json_path, "w") as fid:
            json.dump(envvar_dict, fid)
            fid.write("\n")


        # TODO: handle the case where there is no matching view description
        meta["views"][name]["json"] = envvar_dict
        meta["views"][name]["type"] = "spack-view"

    # process spack and modules
    if args.modules:
        module_path = f"{args.mount}/modules"
        meta["views"]["modules"] = {
            "activate": None,
            "description": "activate modules",
            "root": module_path,
            "json": {
                "version": 1,
                "values": {
                    "list": {
                        "MODULEPATH": [
                            {
                                "op": "prepend",
                                "value": [module_path]
                            }
                        ]
                    },
                    "scalar": {}
                }
            }
        }
    if args.spack is not None:
        url, version = args.spack.split(',')
        spack_path = f"{args.mount}/config".replace("//", "/")
        meta["views"]["spack"] = {
            "activate": None,
            "description": "configure spack upstream",
            "root": spack_path,
            "json": {
                "version": 1,
                "values": {
                    "list": {},
                    "scalar": {
                        "SPACK_SYSTEM_CONFIG_PATH": spack_path,
                        "UENV_SPACK_CONFIG_PATH": spack_path,
                        "UENV_SPACK_COMMIT": version,
                        "UENV_SPACK_URL": url
                    }
                }
            }
        }

    # update the uenv meta data file with the new env. variable description
    with open(meta_path, "w") as fid:
        # write updated meta data
        json.dump(meta, fid)
        fid.write("\n")

if __name__ == "__main__":
    #impl1()
    impl2()