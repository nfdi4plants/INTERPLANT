"""L1 collection descriptors must validate against their schema."""
from __future__ import annotations

import jsonschema
import pytest


@pytest.mark.parametrize("name", ["collection-proteomics.yaml", "collection-fieldtrials.yaml"])
def test_example_validates(schema_collection, load_yaml, name):
    instance = load_yaml(f"examples/{name}")
    jsonschema.Draft202012Validator(schema_collection).validate(instance)


def test_schema_is_valid_jsonschema(schema_collection):
    jsonschema.Draft202012Validator.check_schema(schema_collection)
