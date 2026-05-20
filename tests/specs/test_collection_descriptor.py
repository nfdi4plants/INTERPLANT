"""L1 collection descriptors must validate against their schema."""
from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator

_FC = Draft202012Validator.FORMAT_CHECKER


@pytest.mark.parametrize("name", ["collection-proteomics.yaml", "collection-fieldtrials.yaml"])
def test_example_validates(schema_collection, load_yaml, name):
    instance = load_yaml(f"examples/{name}")
    Draft202012Validator(schema_collection, format_checker=_FC).validate(instance)


def test_schema_is_valid_jsonschema(schema_collection):
    Draft202012Validator.check_schema(schema_collection)
