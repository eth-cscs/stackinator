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


class ValidationError(jsonschema.ValidationError):
    def __init__(self, name: str, errors: list[jsonschema.ValidationError]):
        assert len(errors) != 0
        messages = [
            f"- Failed validating '{error.validator}' in {error.json_path} : {error.message}" for error in errors
        ]
        message = f"ValidationError for '{name}'\n"
        message += "\n".join(messages)
        super().__init__(message)


class SchemaValidator:
    def __init__(self, schema_filepath: pathlib.Path):
        self._validator = validator(json.load(open(schema_filepath)))

    def validate(self, instance: dict):
        errors = [error for error in self._validator.iter_errors(instance)]

        if len(errors) != 0:
            raise ValidationError(self._validator.schema.get("title", "no-title"), errors)


ConfigValidator = SchemaValidator(prefix / "schema/config.json")
CompilersValidator = SchemaValidator(prefix / "schema/compilers.json")
EnvironmentsValidator = SchemaValidator(prefix / "schema/environments.json")
CacheValidator = SchemaValidator(prefix / "schema/cache.json")
