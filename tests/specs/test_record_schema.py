"""The L2 record schema must accept every canonical example."""
from __future__ import annotations

from jsonschema import Draft202012Validator

_FC = Draft202012Validator.FORMAT_CHECKER


def test_complete_example_validates(schema_record, load_json):
    instance = load_json("examples/record-complete.json")
    schema, registry = schema_record
    Draft202012Validator(schema, registry=registry, format_checker=_FC).validate(instance)


def test_partial_example_validates(schema_record, load_json):
    instance = load_json("examples/record-partial.json")
    schema, registry = schema_record
    Draft202012Validator(schema, registry=registry, format_checker=_FC).validate(instance)


def test_fieldtrial_example_validates(schema_record, load_json):
    instance = load_json("examples/record-fieldtrial.json")
    schema, registry = schema_record
    Draft202012Validator(schema, registry=registry, format_checker=_FC).validate(instance)


def test_schema_is_valid_jsonschema(schema_record):
    schema, _registry = schema_record
    Draft202012Validator.check_schema(schema)
