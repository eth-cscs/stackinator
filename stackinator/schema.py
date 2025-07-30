import json
import pathlib

import jsonschema
import yaml

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


def validator_from_schemafile(schema_filepath):
    """
    Create a new validator class given the schema filepath.
    See validator function for details.
    """
    return validator(json.load(open(schema_filepath)))


def validate(schema_validator, instance):
    """
    Validate an instance of a schema against a given schema_validator class.

    It prints all errors detected during validation and then it raises the first one.
    """
    errors = [error for error in schema_validator.iter_errors(instance)]
    if len(errors) != 0:
        for error in errors:
            print(error.json_path, error.message)
        raise errors[0]


ConfigValidator = validator_from_schemafile(prefix / "schema/config.json")
CompilersValidator = validator_from_schemafile(prefix / "schema/compilers.json")
EnvironmentsValidator = validator_from_schemafile(prefix / "schema/environments.json")
CacheValidator = validator_from_schemafile(prefix / "schema/cache.json")
