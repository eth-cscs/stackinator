import json
import pathlib
from textwrap import dedent

import jsonschema
import yaml

from . import root_logger

prefix = pathlib.Path(__file__).parent.resolve()


def py2yaml(data, indent):
    dump = yaml.dump(data)
    lines = [ln for ln in dump.split("\n") if ln != ""]
    res = ("\n" + " " * indent).join(lines)
    return res


def validator(schema):
    """
    Create a new validator class that will insert optional fields with their default values
    if they have not been provided.
    """

    def extend_with_default(validator_class):
        validate_properties = validator_class.VALIDATORS["properties"]

        def set_defaults(validator, properties, instance, schema):
            # if instance is none, it's not possible to set any default for any sub-property
            if instance is not None:
                for property, subschema in properties.items():
                    if "default" in subschema:
                        instance.setdefault(property, subschema["default"])

            for error in validate_properties(
                validator,
                properties,
                instance,
                schema,
            ):
                yield error

        return jsonschema.validators.extend(
            validator_class,
            {"properties": set_defaults},
        )

    # try to read dialect metaschema from the $schema entry, otherwise fallback to a default one.
    metaschema = jsonschema.validators.validator_for(schema)

    return extend_with_default(metaschema)(schema)


class ValidationError(jsonschema.ValidationError):
    def __init__(self, name: str, errors: list[jsonschema.ValidationError]):
        assert len(errors) != 0
        messages = [
            f"- Failed validating '{error.validator}' in {error.json_path} : {error.message}" for error in errors
        ]
        message = f"ValidationError in '{name}'\n"
        message += "\n".join(messages)
        super().__init__(message)


class SchemaValidator:
    def __init__(self, schema_filepath: pathlib.Path, precheck=None, postcheck=None, postcheck_args=()):
        self._validator = validator(json.load(open(schema_filepath)))
        self._precheck = precheck
        self._postcheck = postcheck
        self._postcheck_args = postcheck_args

    def validate(self, instance: dict):
        if self._precheck:
            self._precheck(instance)

        errors = [error for error in self._validator.iter_errors(instance)]

        if len(errors) != 0:
            raise ValidationError(self._validator.schema.get("title", "no-title"), errors)

        if self._postcheck:
            self._postcheck(instance, *self._postcheck_args)


def check_config_version(instance):
    rversion = instance.get("version", 1)
    if rversion != 2:
        if rversion == 1:
            root_logger.error(
                dedent("""
                       The recipe is an old version 1 recipe for Spack v0.23 and earlier.
                       This version of Stackinator supports Spack 1.0, and has deprecated support for Spack v0.23.
                       Use version 5 of stackinator, which can be accessed via the releases/v5 branch:
                       git switch releases/v5

                       If this recipe is to be used with Spack 1.0, then please add the field 'version: 2' to
                       config.yaml in your recipe.

                       For more information: https://eth-cscs.github.io/stackinator/recipes/#configuration
                       """)
            )
            raise RuntimeError("incompatible uenv recipe version")
        else:
            root_logger.error(
                dedent(f"""
                       The config.yaml file sets an unknown recipe version={rversion}.
                       This version of Stackinator supports version 2 recipes.

                       For more information: https://eth-cscs.github.io/stackinator/recipes/#configuration
                       """)
            )
            raise RuntimeError("incompatible uenv recipe version")


ConfigValidator = SchemaValidator(prefix / "schema/config.json", check_config_version)
CompilersValidator = SchemaValidator(prefix / "schema/compilers.json")
EnvironmentsValidator = SchemaValidator(prefix / "schema/environments.json")
CacheValidator = SchemaValidator(prefix / "schema/cache.json")


def modules_constraints(instance: dict, mount: pathlib.Path):
    # Note:
    # modules root should match MODULEPATH set by envvars and used by uenv view "modules"
    # so we enforce that the user does not override it in modules.yaml
    instance["modules"].setdefault("default", {}).setdefault("roots", {}).setdefault(
        "tcl", (mount / "modules").as_posix()
    )


def ModulesValidator(mountpoint):
    return SchemaValidator(
        prefix / "schema/modules.json", None, postcheck=modules_constraints, postcheck_args=(mountpoint,)
    )
