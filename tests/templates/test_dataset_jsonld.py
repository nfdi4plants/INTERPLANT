"""The server-rendered schema.org Dataset block (spec section 8, R6, R7)."""
from __future__ import annotations

from .builders import ITEM_TPL, MULTIPOINT, POINT, dataset_jsonld, item_data


def test_point_becomes_geocoordinates(render):
    dataset = dataset_jsonld(render(ITEM_TPL, item_data(geometry=POINT)))
    assert dataset["spatialCoverage"] == {
        "@type": "Place",
        "geo": {"@type": "GeoCoordinates", "latitude": 51.1889, "longitude": 6.7926},
    }


def test_multipoint_becomes_a_lat_lon_box(render):
    dataset = dataset_jsonld(render(ITEM_TPL, item_data(geometry=MULTIPOINT)))
    # schema.org GeoShape.box: "minLat minLon maxLat maxLon"
    assert dataset["spatialCoverage"] == {
        "@type": "Place",
        "geo": {"@type": "GeoShape", "box": "-28.566667 -70.783333 51.826197 101.13511"},
    }


def test_no_spatial_coverage_without_geometry(render):
    assert "spatialCoverage" not in dataset_jsonld(render(ITEM_TPL, item_data(geometry=None)))


def test_unsupported_geometry_emits_no_spatial_coverage(render):
    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
    assert "spatialCoverage" not in dataset_jsonld(render(ITEM_TPL, item_data(geometry=polygon)))


def test_identifier_is_the_uuid(render):
    dataset = dataset_jsonld(render(ITEM_TPL, item_data()))
    assert dataset["identifier"] == "ef4702a2-deeb-51f6-8042-de011f4e4e5b"


def test_null_external_id_is_neither_shown_nor_emitted(render):
    html = render(
        ITEM_TPL,
        item_data(record_id="dataplant-no-uuid",
                  externalIds=[{"scheme": "urn:uuid", "value": None}]),
    )
    assert "urn:uuid:None" not in html
    assert "External identifiers" not in html
    assert dataset_jsonld(html)["identifier"] == "dataplant-no-uuid"


def test_required_dataset_fields_present(render):
    dataset = dataset_jsonld(render(ITEM_TPL, item_data()))
    assert dataset["@type"] == "Dataset"
    for key in ("name", "description", "url", "license", "creator", "distribution"):
        assert dataset[key], key
