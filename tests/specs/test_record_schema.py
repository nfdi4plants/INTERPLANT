"""The L2 record schema must accept every canonical example."""
from __future__ import annotations

from jsonschema import Draft202012Validator


def test_complete_example_validates(validate_record, load_json):
    instance = load_json("examples/record-complete.json")
    validate_record(instance)


def test_partial_example_validates(validate_record, load_json):
    instance = load_json("examples/record-partial.json")
    validate_record(instance)


def test_fieldtrial_example_validates(validate_record, load_json):
    instance = load_json("examples/record-fieldtrial.json")
    validate_record(instance)


def test_schema_is_valid_jsonschema(schema_record):
    schema, _ = schema_record
    Draft202012Validator.check_schema(schema)
