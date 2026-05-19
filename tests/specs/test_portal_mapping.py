"""Mapper output must validate against the pinned portal DocumentSchema.json."""
from __future__ import annotations

from jsonschema import Draft202012Validator

_FC = Draft202012Validator.FORMAT_CHECKER


def test_mapped_example_validates_against_portal_schema(schema_portal, load_json):
    mapped = load_json("examples/portal-document-chlamy.json")
    Draft202012Validator(schema_portal, format_checker=_FC).validate(mapped)


def test_mapper_reference_impl_matches_fixture(load_json):
    """The reference mapper's output on the canonical input must equal the committed fixture."""
    from scripts.portal_mapper import map_record

    record = load_json("examples/record-complete.json")
    produced = map_record(record)
    expected = load_json("examples/portal-document-chlamy.json")
    assert produced == expected


def test_portal_schema_is_valid(schema_portal):
    Draft202012Validator.check_schema(schema_portal)
