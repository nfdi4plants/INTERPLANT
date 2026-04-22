"""Shared fixtures for spec validation tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

SPECS_ROOT = Path(__file__).parent.parent.parent / "docs" / "specs"
SCHEMAS_DIR = SPECS_ROOT / "schemas"
EXAMPLES_DIR = SPECS_ROOT / "examples"


@pytest.fixture
def load_json():
    def _load(relative: str) -> dict:
        return json.loads((SPECS_ROOT / relative).read_text())

    return _load


@pytest.fixture
def load_yaml():
    def _load(relative: str) -> dict:
        return yaml.safe_load((SPECS_ROOT / relative).read_text())

    return _load


@pytest.fixture
def schema_record(load_json):
    return load_json("schemas/record.schema.json")


@pytest.fixture
def schema_collection(load_json):
    return load_json("schemas/collection-descriptor.schema.json")


@pytest.fixture
def schema_portal(load_json):
    return load_json("schemas/portal-document-schema.json")
