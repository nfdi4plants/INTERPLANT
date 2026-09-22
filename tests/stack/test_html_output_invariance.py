"""The template overrides must change ?f=html and nothing else.

These assertions are the contract from the design spec: JSON, JSON-LD and
GeoJSON output, URLs and status codes stay exactly as pygeoapi produces them.
"""
from __future__ import annotations

import pytest
import requests

COLLECTION = "arc-records"

PATHS = [
    "/",
    "/collections",
    f"/collections/{COLLECTION}",
    f"/collections/{COLLECTION}/items",
    "/conformance",
]


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("fmt", ["json", "jsonld"])
def test_non_html_formats_stay_machine_readable(
    pygeoapi_url: str, pygeoapi_reachable: bool, path: str, fmt: str
):
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    resp = requests.get(f"{pygeoapi_url}{path}", params={"f": fmt}, timeout=30)
    assert resp.status_code == 200
    assert "json" in resp.headers["content-type"]
    payload = resp.json()
    assert payload, f"{path}?f={fmt} returned an empty body"
    # No template output may leak into a machine format.
    assert "dp-card" not in resp.text
    assert "dataplant.css" not in resp.text


def test_item_json_keeps_its_ogc_shape(pygeoapi_url: str, pygeoapi_reachable: bool):
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    items = requests.get(
        f"{pygeoapi_url}/collections/{COLLECTION}/items",
        params={"limit": 1, "f": "json"},
        timeout=30,
    ).json()
    if not items["features"]:
        pytest.skip("no records loaded in this stack")
    item_id = items["features"][0]["id"]
    item = requests.get(
        f"{pygeoapi_url}/collections/{COLLECTION}/items/{item_id}",
        params={"f": "json"},
        timeout=30,
    ).json()
    assert item["type"] == "Feature"
    assert set(["id", "properties", "geometry", "links"]) <= set(item)
    assert "geometry" in item, "geometry key must be present even when null"


def test_html_is_the_only_changed_representation(
    pygeoapi_url: str, pygeoapi_reachable: bool
):
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    html = requests.get(
        f"{pygeoapi_url}/collections/{COLLECTION}/items",
        params={"limit": 1, "f": "html"},
        timeout=30,
    )
    assert html.status_code == 200
    assert "text/html" in html.headers["content-type"]
    assert "dataplant.css" in html.text
