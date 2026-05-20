"""L1 collection descriptors must validate against their schema."""
from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator


@pytest.mark.parametrize("name", ["collection-proteomics.yaml", "collection-fieldtrials.yaml"])
def test_example_validates(schema_collection, load_yaml, validate_against, name):
    instance = load_yaml(f"examples/{name}")
    validate_against(schema_collection, instance)


def test_schema_is_valid_jsonschema(schema_collection):
    Draft202012Validator.check_schema(schema_collection)
