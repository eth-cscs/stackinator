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

# name: cuda-env
# # default /user-environment
# store: /user-environment
# system: hohgant
# spack:
#     repo: https://github.com/spack/spack.git
#     # default: None == no `git checkout` command
#     commit: 6408b51
# mirror:
#     # default None
#     key: /home/bob/veryprivate.key
#     # default True
#     enable: True
# # default True
# modules: False

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
            }
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

