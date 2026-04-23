"""The L2 record schema must accept every canonical example."""
from __future__ import annotations

import jsonschema
import pytest


def test_complete_example_validates(schema_record, load_json):
    instance = load_json("examples/record-complete.json")
    jsonschema.Draft202012Validator(schema_record).validate(instance)


def test_partial_example_validates(schema_record, load_json):
    instance = load_json("examples/record-partial.json")
    jsonschema.Draft202012Validator(schema_record).validate(instance)


def test_fieldtrial_example_validates(schema_record, load_json):
    instance = load_json("examples/record-fieldtrial.json")
    jsonschema.Draft202012Validator(schema_record).validate(instance)


def test_schema_is_valid_jsonschema(schema_record):
    jsonschema.Draft202012Validator.check_schema(schema_record)
