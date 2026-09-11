"""Tests for per-study event geometry in the portal mapping."""
from __future__ import annotations

from oai.mapping import map_record


def _record(locations: list[dict], studies: list[dict], geometry: dict | None) -> dict:
    return {
        "id": "dataplant-x",
        "type": "Feature",
        "geometry": geometry,
        "time": {"interval": [None, None]},
        "properties": {
            "title": "t", "description": "d", "created": "2026-01-01T00:00:00Z",
            "updated": "2026-01-01T00:00:00Z", "keywords": [], "license": "CC-BY-4.0",
            "arc_source_uri": "https://git.nfdi4plants.org/ns/arc",
            "uniqueId": "00000000-0000-0000-0000-000000000000",
            "record_quality": "partial", "harvested_at": "2026-01-01T00:00:00Z",
            "harvester_version": "0.1.0", "contacts": [], "creators": [],
            "publications": [], "omics_domains": ["other"],
            "experiment_context": "lab", "organism": [], "project": [],
            "studies": studies, "assays": [],
            "location_status": "extracted", "locations": locations,
        },
        "links": [],
    }


def test_each_study_gets_its_own_geometry() -> None:
    record = _record(
        locations=[
            {"role": "experiment-site", "label": None, "label_field": None,
             "point": [6.0, 51.0], "precision": "exact", "n_rows": 1,
             "source": "studies/site_a/isa.study.xlsx#t"},
            {"role": "experiment-site", "label": None, "label_field": None,
             "point": [11.0, 48.0], "precision": "exact", "n_rows": 1,
             "source": "studies/site_b/isa.study.xlsx#t"},
        ],
        studies=[{"id": "site_a", "title": "A"}, {"id": "site_b", "title": "B"}],
        geometry={"type": "MultiPoint", "coordinates": [[6.0, 51.0], [11.0, 48.0]]},
    )
    events = {e["id"]: e for e in map_record(record)["events"]}
    assert events["site_a"]["geometry"] == {"type": "Point", "coordinates": [6.0, 51.0]}
    assert events["site_b"]["geometry"] == {"type": "Point", "coordinates": [11.0, 48.0]}


def test_a_study_with_no_points_falls_back_to_the_record_geometry() -> None:
    record = _record(
        locations=[
            {"role": "custodian-institution", "label": "HHU",
             "label_field": "Investigation Person Affiliation",
             "point": [6.7926, 51.1889], "precision": "institution", "n_rows": 1,
             "source": "affiliation"},
        ],
        studies=[{"id": "only", "title": "O"}],
        geometry={"type": "Point", "coordinates": [6.7926, 51.1889]},
    )
    event = map_record(record)["events"][0]
    assert event["geometry"] == {"type": "Point", "coordinates": [6.7926, 51.1889]}


def test_no_geometry_key_when_the_record_has_none() -> None:
    # portal-mapping.md: geometry null means omit the key entirely.
    record = _record(locations=[], studies=[{"id": "s", "title": "S"}], geometry=None)
    record["properties"]["location_status"] = "absent"
    assert "geometry" not in map_record(record)["events"][0]


def test_a_point_merged_across_two_studies_attributes_to_both() -> None:
    # harvester.extractors.location merges an identical (role, point) seen in
    # several tables, joining their source paths with "; ". A source that
    # names two studies must attribute the point to both, not just the first.
    # Record-level geometry is deliberately None so a study wrongly falling
    # back to it (instead of its own point) shows up as a missing key rather
    # than a value that happens to match.
    record = _record(
        locations=[
            {"role": "experiment-site", "label": None, "label_field": None,
             "point": [6.0, 51.0], "precision": "exact", "n_rows": 2,
             "source": "studies/site_a/isa.study.xlsx#t; studies/site_b/isa.study.xlsx#t"},
        ],
        studies=[{"id": "site_a", "title": "A"}, {"id": "site_b", "title": "B"}],
        geometry=None,
    )
    events = {e["id"]: e for e in map_record(record)["events"]}
    assert events["site_a"]["geometry"] == {"type": "Point", "coordinates": [6.0, 51.0]}
    assert events["site_b"]["geometry"] == {"type": "Point", "coordinates": [6.0, 51.0]}


def test_study_geometry_respects_the_records_winning_tier() -> None:
    # harvester.extractors.location.derive_geometry filters record geometry to
    # the winning precedence tier (extracted > geocoded > institution); event
    # geometry must respect the same precedence rather than mixing tiers just
    # because both points happen to attribute to the same study.
    record = _record(
        locations=[
            {"role": "experiment-site", "label": None, "label_field": None,
             "point": [6.0, 51.0], "precision": "exact", "n_rows": 1,
             "source": "studies/site_a/isa.study.xlsx#t"},
            {"role": "stated-place", "label": "Somewhere", "label_field": "Country",
             "point": [11.0, 48.0], "precision": "country", "n_rows": 1,
             "source": "studies/site_a/isa.study.xlsx#t"},
        ],
        studies=[{"id": "site_a", "title": "A"}],
        geometry={"type": "Point", "coordinates": [6.0, 51.0]},
    )
    assert record["properties"]["location_status"] == "extracted"
    event = map_record(record)["events"][0]
    assert event["geometry"] == {"type": "Point", "coordinates": [6.0, 51.0]}


def test_a_merged_source_with_an_assay_segment_still_attributes_to_its_study() -> None:
    # An assay-then-study merged source must not fail the startswith("studies/")
    # check just because the first segment is not a study. Record-level
    # geometry is None for the same reason as above.
    record = _record(
        locations=[
            {"role": "experiment-site", "label": None, "label_field": None,
             "point": [6.0, 51.0], "precision": "exact", "n_rows": 2,
             "source": "assays/flyover_2025_01/isa.assay.xlsx#t; studies/site_a/isa.study.xlsx#t"},
        ],
        studies=[{"id": "site_a", "title": "A"}],
        geometry=None,
    )
    event = map_record(record)["events"][0]
    assert event["geometry"] == {"type": "Point", "coordinates": [6.0, 51.0]}