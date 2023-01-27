import json
import jsonschema
import pathlib
import yaml

prefix = pathlib.Path(__file__).parent.resolve()

# create a validator that will insert optional fields with their default values
# if they have not been provided.

def extend_with_default(validator_class):
    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(validator, properties, instance, schema):
        for property, subschema in properties.items():
            if "default" in subschema:
                instance.setdefault(property, subschema["default"])

        for error in validate_properties(
            validator, properties, instance, schema,
        ):
            yield error

    return jsonschema.validators.extend(
        validator_class, {"properties" : set_defaults},
    )

validator = extend_with_default(jsonschema.Draft7Validator)

# load recipe yaml schema
config_schema = json.load(open(prefix / 'schema/config.json'))
compilers_schema = json.load(open(prefix / 'schema/compilers.json'))
