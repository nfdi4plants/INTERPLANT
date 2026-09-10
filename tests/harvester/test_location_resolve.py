"""Tests for fallback resolution, the precedence chain and geometry derivation."""
from __future__ import annotations

from harvester.extractors.location import (
    arc_path_from_uri,
    derive_geometry,
    resolve_locations,
)
from harvester.isa_reader import Contact, Investigation, Table


def _inv(*, tables=None, contacts=None) -> Investigation:
    return Investigation(
        identifier="i",
        title="t",
        description=None,
        contacts=contacts or [],
        tables=tables or [],
    )


def _contact(affiliation: str | None) -> Contact:
    return Contact(
        first_name="A", last_name="B", email=None, orcid=None, affiliation=affiliation
    )


def _coord_table() -> Table:
    return Table(
        name="s",
        source="studies/s/isa.study.xlsx#s",
        headers=["Parameter [Biological material latitude]",
                 "Parameter [Biological material longitude]"],
        columns=[["51.1889"], ["6.7926"]],
    )


def _place_table() -> Table:
    return Table(
        name="s",
        source="studies/s/isa.study.xlsx#s",
        headers=["Characteristic [geographic location]"],
        columns=[["Germany"]],
    )


def test_arc_path_from_uri_strips_the_gitlab_base() -> None:
    assert arc_path_from_uri(
        "https://git.nfdi4plants.org/usadellab/Teosinte"
    ) == "usadellab/Teosinte"
    assert arc_path_from_uri(
        "https://git.nfdi4plants.org/DiP/DiP-KS/dip-ressourcen"
    ) == "DiP/DiP-KS/dip-ressourcen"


def test_arc_path_from_uri_returns_none_for_a_local_file_uri() -> None:
    # Local ARCs cannot match a curated override; they get "unspecified".
    assert arc_path_from_uri("file:///home/mohamed/ARCs/ArcPrototype-main") is None


def test_extracted_coordinates_win_the_precedence_chain() -> None:
    inv = _inv(tables=[_coord_table(), _place_table()],
               contacts=[_contact("Heinrich Heine University")])
    locations, status = resolve_locations(inv, arc_source_uri="https://x/y/z")
    assert status == "extracted"
    # every tier is still recorded
    roles = {loc["role"] for loc in locations}
    assert "material-origin" in roles
    assert "stated-place" in roles
    assert "custodian-institution" in roles


def test_place_name_outranks_affiliation() -> None:
    inv = _inv(tables=[_place_table()], contacts=[_contact("Heinrich Heine University")])
    locations, status = resolve_locations(inv, arc_source_uri="https://x/y/z")
    assert status == "geocoded"


def test_affiliation_is_used_when_nothing_else_exists() -> None:
    inv = _inv(contacts=[_contact("Heinrich Heine University")])
    locations, status = resolve_locations(inv, arc_source_uri="https://x/y/z")
    assert status == "institution"
    assert locations[0]["role"] == "custodian-institution"
    assert locations[0]["precision"] == "institution"


def test_absent_when_no_source_yields_anything() -> None:
    inv = _inv(contacts=[_contact(None)])
    locations, status = resolve_locations(inv, arc_source_uri="https://x/y/z")
    assert status == "absent"
    assert locations == []


def test_an_unresolvable_affiliation_yields_absent() -> None:
    # AFFILIATION_PERSON2 is a template placeholder recorded as an explicit null.
    inv = _inv(contacts=[_contact("AFFILIATION_PERSON2")])
    _, status = resolve_locations(inv, arc_source_uri="https://x/y/z")
    assert status == "absent"


def test_a_multi_institution_affiliation_splits_on_semicolons() -> None:
    inv = _inv(contacts=[
        _contact("Heinrich Heine University;Max Planck Institute of Molecular Plant Physiology")
    ])
    locations, status = resolve_locations(inv, arc_source_uri="https://x/y/z")
    assert status == "institution"
    assert len({tuple(loc["point"]) for loc in locations}) == 2


def test_curated_role_reaches_ad_hoc_coordinates() -> None:
    table = Table(
        name="s",
        source="studies/s/isa.study.xlsx#s",
        headers=["Parameter [latitude]", "Parameter [longitude]"],
        columns=[["18.485833"], ["-99.791667"]],
    )
    inv = _inv(tables=[table])
    locations, _ = resolve_locations(
        inv, arc_source_uri="https://git.nfdi4plants.org/usadellab/Teosinte"
    )
    assert locations[0]["role"] == "collection-site"


def test_derive_geometry_returns_a_point_when_all_points_agree() -> None:
    locations = [
        {"role": "experiment-site", "point": [6.0, 51.0], "precision": "exact"},
        {"role": "experiment-site", "point": [6.0, 51.0], "precision": "exact"},
    ]
    assert derive_geometry(locations, "extracted") == {
        "type": "Point", "coordinates": [6.0, 51.0]
    }


def test_derive_geometry_returns_multipoint_when_points_differ() -> None:
    locations = [
        {"role": "collection-site", "point": [6.0, 51.0], "precision": "exact"},
        {"role": "collection-site", "point": [7.0, 52.0], "precision": "exact"},
    ]
    geometry = derive_geometry(locations, "extracted")
    assert geometry["type"] == "MultiPoint"
    assert geometry["coordinates"] == [[6.0, 51.0], [7.0, 52.0]]


def test_derive_geometry_never_returns_a_polygon() -> None:
    # dormancy_NhuTran_2025 spans 259 degrees of longitude. A bbox Polygon
    # would match nearly every spatial query while being confidently wrong.
    locations = [
        {"role": "collection-site", "point": [-123.21, 35.01], "precision": "exact"},
        {"role": "collection-site", "point": [135.75, 62.88], "precision": "exact"},
    ]
    assert derive_geometry(locations, "extracted")["type"] == "MultiPoint"


def test_derive_geometry_uses_only_the_winning_tier() -> None:
    locations = [
        {"role": "experiment-site", "point": [6.0, 51.0], "precision": "exact"},
        {"role": "custodian-institution", "point": [13.0, 52.4],
         "precision": "institution"},
    ]
    assert derive_geometry(locations, "extracted") == {
        "type": "Point", "coordinates": [6.0, 51.0]
    }


def test_derive_geometry_is_null_when_absent() -> None:
    assert derive_geometry([], "absent") is None
