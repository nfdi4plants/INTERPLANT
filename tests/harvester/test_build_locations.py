"""Tests for location fields in an assembled L2 record."""
from __future__ import annotations

from harvester.build import build_record
from harvester.isa_reader import Assay, Contact, Investigation, Study, Table


def _build(*, tables=None, contacts=None, uri="https://git.nfdi4plants.org/ns/arc") -> dict:
    # record.schema.json sets minItems: 1 on BOTH omics_domains and assays, so a
    # record with no assays fails validation for reasons unrelated to locations.
    # One classified assay satisfies both.
    inv = Investigation(
        identifier="arc",
        title="An ARC",
        description="d",
        contacts=contacts or [],
        studies=[
            Study(
                identifier="s1",
                title="S1",
                assays=[Assay(name="rna", folder="rna", measurement_type=None)],
            )
        ],
        tables=tables or [],
    )
    return build_record(
        inv,
        {"rna": "transcriptomics"},
        arc_source_uri=uri,
        harvested_at="2026-09-09T00:00:00Z",
        created="2026-09-09T00:00:00Z",
        updated="2026-09-09T00:00:00Z",
    )


def test_a_record_without_locations_is_absent_and_null() -> None:
    record = _build()
    assert record["geometry"] is None
    assert record["properties"]["location_status"] == "absent"
    assert record["properties"]["locations"] == []


def test_locations_is_always_present_even_when_empty() -> None:
    # Follows the `keywords` precedent: always present, possibly empty.
    assert "locations" in _build()["properties"]


def test_extracted_coordinates_become_the_record_geometry() -> None:
    table = Table(
        name="s",
        source="studies/s/isa.study.xlsx#s",
        headers=["Parameter [Biological material latitude]",
                 "Parameter [Biological material longitude]"],
        columns=[["51.1889"], ["6.7926"]],
    )
    record = _build(tables=[table])
    assert record["properties"]["location_status"] == "extracted"
    assert record["geometry"] == {"type": "Point", "coordinates": [6.7926, 51.1889]}
    assert record["properties"]["locations"][0]["role"] == "material-origin"


def test_geojson_axis_order_is_longitude_then_latitude() -> None:
    table = Table(
        name="s",
        source="studies/s/isa.study.xlsx#s",
        headers=["Parameter [latitude]", "Parameter [longitude]"],
        columns=[["18.485833"], ["-99.791667"]],
    )
    record = _build(tables=[table])
    lon, lat = record["geometry"]["coordinates"]
    assert lon == -99.791667
    assert lat == 18.485833


def test_affiliation_fallback_fills_geometry() -> None:
    contact = Contact(
        first_name="A", last_name="B", email=None, orcid=None,
        affiliation="Heinrich Heine University",
    )
    record = _build(contacts=[contact])
    assert record["properties"]["location_status"] == "institution"
    assert record["geometry"]["type"] == "Point"


def test_record_validates_against_the_l2_schema(validate_record) -> None:
    validate_record(_build())