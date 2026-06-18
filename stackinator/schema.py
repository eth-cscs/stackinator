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
    def __init__(self, schema_filepath: pathlib.Path, precheck=None):
        self._validator = validator(json.load(open(schema_filepath)))
        self._precheck = precheck

    def validate(self, instance: dict):
        if self._precheck:
            self._precheck(instance)

        errors = [error for error in self._validator.iter_errors(instance)]

        if len(errors) != 0:
            raise ValidationError(self._validator.schema.get("title", "no-title"), errors)


def check_config_version(instance):
    rversion = instance.get("version", 1)
    if rversion != 3:
        if rversion in (1, 2):
            root_logger.error(
                dedent(f"""
                       The recipe uses version {rversion} of the uenv recipe format.
                       Stackinator v7 only supports version 3 recipes (Spack 1.2+).

                       To build version {rversion} recipes, use Stackinator v6:
                       git switch releases/v6

                       To port this recipe to version 3, see:
                       https://eth-cscs.github.io/stackinator/porting/
                       """)
            )
            raise RuntimeError("incompatible uenv recipe version")
        else:
            root_logger.error(
                dedent(f"""
                       The config.yaml file sets an unknown recipe version={rversion}.
                       Stackinator v7 supports version 3 recipes.

                       For more information: https://eth-cscs.github.io/stackinator/recipes/#configuration
                       """)
            )
            raise RuntimeError("incompatible uenv recipe version")


def check_module_paths(instance):
    try:
        instance["modules"]["default"]["roots"]["tcl"]
        root_logger.warning("'modules:default:roots:tcl' field is ignored and overwritten by stackinator.")
    except KeyError:
        pass


ConfigValidator = SchemaValidator(prefix / "schema/config.json", check_config_version)
CompilersValidator = SchemaValidator(prefix / "schema/compilers.json")
EnvironmentsValidator = SchemaValidator(prefix / "schema/environments.json")
CacheValidator = SchemaValidator(prefix / "schema/cache.json")
ModulesValidator = SchemaValidator(prefix / "schema/modules.json", check_module_paths)
MirrorsValidator = SchemaValidator(prefix / "schema/mirror.json")
