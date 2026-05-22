"""Shared fixtures for spec validation tests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SPECS_ROOT = Path(__file__).parent.parent / "docs" / "specs"
SCHEMAS_DIR = SPECS_ROOT / "schemas"
EXAMPLES_DIR = SPECS_ROOT / "examples"

_FORMAT_CHECKER = Draft202012Validator.FORMAT_CHECKER


@pytest.fixture
def load_json():
    def _load(relative: str) -> Any:
        return json.loads((SPECS_ROOT / relative).read_text(encoding="utf-8"))

    return _load


@pytest.fixture
def load_yaml():
    def _load(relative: str) -> Any:
        return yaml.safe_load((SPECS_ROOT / relative).read_text(encoding="utf-8"))

    return _load


@pytest.fixture
def schema_record(load_json) -> tuple[dict[str, Any], Registry]:
    record = load_json("schemas/record.schema.json")
    extensions = load_json("schemas/assay-extensions.schema.json")
    registry: Registry = Registry().with_resource(
        "https://interplant.org/schemas/assay-extensions.schema.json",
        Resource.from_contents(extensions),
    )
    return record, registry


@pytest.fixture
def schema_collection(load_json) -> dict[str, Any]:
    return load_json("schemas/collection-descriptor.schema.json")


@pytest.fixture
def schema_portal(load_json) -> dict[str, Any]:
    return load_json("schemas/portal-document-schema.json")


@pytest.fixture
def validate_record(schema_record):
    """Return a callable that validates instances against the record schema.

    Centralizes validator construction so individual tests cannot drop `format_checker`.
    """
    schema, registry = schema_record

    def _validate(instance: Any) -> None:
        Draft202012Validator(
            schema, registry=registry, format_checker=_FORMAT_CHECKER
        ).validate(instance)

    return _validate


@pytest.fixture
def validate_against():
    """Return a callable that validates instances against a registry-less schema."""

    def _validate(schema: dict[str, Any], instance: Any) -> None:
        Draft202012Validator(schema, format_checker=_FORMAT_CHECKER).validate(instance)

    return _validate
