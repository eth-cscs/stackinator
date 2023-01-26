import jsonschema
import yaml

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

# for config.yaml files
config_schema = {
    "type" : "object",
    "properties" : {
        "name" : {
            "type": "string"
        },
        "store" : {
            "type" : "string",
            "default" : "/user-environment"
        },
        "system" : {
            "type" : "string",
        },
        "spack" : {
            "type" : "object",
            "properties" : {
                "repo": {
                    "type": "string",
                },
                "commit": {
                    "oneOf": [
                        {"type" : "string"},
                        {"type" : "null"},
                    ],
                    "default": None,
                }
            },
            "additionalProperties": False,
        },
        "mirror" : {
            "type" : "object",
            "properties" : {
                "enable" : {
                    "type": "boolean",
                    "default": True,
                },
                "key" : {
                    "oneOf": [
                        {"type" : "string"},
                        {"type" : "null"},
                    ],
                    "default": None,
                }
            },
            "additionalProperties": False,
            "default": {"enable": True, "key": None},
        },
        "modules" : {
            "type": "boolean",
            "default": True,
        },
    },
    # this restricts to only the fields described above
    "additionalProperties": False,
    "required": ["name", "system", "spack"]
}

# for config.yaml files
compilers_schema = {
    "type" : "object",
    "properties" : {
        "bootstrap" : {
            "type": "object",
            "properties": {
                "spec": {
                    "type": "string",
                },
            },
            "additionalProperties": False,
            "required": ["spec"],
        },
        "gcc" : {
            "type": "object",
            "properties": {
                "specs": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                    "minItems": 1,
                },
            },
            "additionalProperties": False,
            "required": ["specs"],
        },
        "llvm" : {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "requires": "string",
                        "specs": {
                            "type": "array",
                            "items": {
                                "type": "string",
                            },
                            "minItems": 1,
                        },
                    },
                    "additionalProperties": False,
                    "required": ["requires", "specs"],
                },
                {
                    "type" : "null"
                },
            ],
            "default": None,
        },
    },
    # this restricts to only the fields described above
    "additionalProperties": False,
    "required": ["bootstrap", "gcc"]
}
