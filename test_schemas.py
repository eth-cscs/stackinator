#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "jsonschema",
# ]
# ///

import pathlib
import json

from jsonschema.validators import validator_for

prefix = pathlib.Path(__file__).parent.resolve() / "stackinator/schema"

if __name__ == "__main__":
    for schema_filepath in prefix.iterdir():
        print(f"checking {schema_filepath}")
        schema = json.load(open(schema_filepath))
        validator = validator_for(schema)
        validator.check_schema(schema)
