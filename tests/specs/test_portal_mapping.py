"""Mapper output must validate against the pinned portal DocumentSchema.json."""
from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator


def test_mapped_example_validates_against_portal_schema(schema_portal, load_json, validate_against):
    mapped = load_json("examples/portal-document-chlamy.json")
    validate_against(schema_portal, mapped)


@pytest.mark.parametrize(
    "record_name",
    ["record-complete.json", "record-partial.json", "record-fieldtrial.json"],
)
def test_mapper_output_validates_for_every_record_fixture(schema_portal, load_json, validate_against, record_name):  # noqa: E501
    """Running the mapper on each canonical record fixture must yield portal-valid output.

    Catches null-handling (record-partial has no DOI, null time interval),
    geometry handling (record-fieldtrial has a non-null geometry), and
    non-DOI publication paths.
    """
    from oai.mapping import map_record

    record = load_json(f"examples/{record_name}")
    produced = map_record(record)
    validate_against(schema_portal, produced)


def test_mapper_reference_impl_matches_fixture(load_json):
    """The reference mapper's output on the canonical input must equal the committed fixture."""
    from oai.mapping import map_record

    record = load_json("examples/record-complete.json")
    produced = map_record(record)
    expected = load_json("examples/portal-document-chlamy.json")
    assert produced == expected


def test_portal_schema_is_valid(schema_portal):
    Draft202012Validator.check_schema(schema_portal)


def test_mapper_emits_organisations_for_provider_and_datacenter(load_json):
    """Records must be attributable in the portal's provider/datacenter facets."""
    from oai.mapping import map_record

    produced = map_record(load_json("examples/record-complete.json"))
    orgs = produced["organisations"]

    assert [o["abbreviation"] for o in orgs["provider"]] == ["DataPLANT"]
    assert [o["abbreviation"] for o in orgs["datacenter"]] == ["FZJ"]
    assert orgs["provider"][0]["url"] == "https://nfdi4plants.org/"
    assert orgs["datacenter"][0]["url"] == "https://www.fz-juelich.de/"


def test_organisations_is_the_same_object_shape_for_every_record_fixture(load_json):
    """It is a constant, so every record carries an identical block."""
    from oai.mapping import map_record

    produced = [
        map_record(load_json(f"examples/{name}"))["organisations"]
        for name in ("record-complete.json", "record-partial.json", "record-fieldtrial.json")
    ]
    assert produced[0] == produced[1] == produced[2]


def test_mapper_does_not_alias_the_organisations_constant(load_json):
    """Mutating one record's output must not corrupt every later record."""
    from oai import mapping

    first = mapping.map_record(load_json("examples/record-complete.json"))
    first["organisations"]["provider"][0]["abbreviation"] = "MUTATED"

    second = mapping.map_record(load_json("examples/record-complete.json"))
    assert second["organisations"]["provider"][0]["abbreviation"] == "DataPLANT"
