"""HTML behaviour of the DataPLANT-branded pages, against the running stack."""
from __future__ import annotations

import pytest
import requests

COLLECTION = "arc-records"


def _get(url: str, **params) -> requests.Response:
    params.setdefault("f", "html")
    return requests.get(url, params=params, timeout=30)


@pytest.fixture
def item_id(pygeoapi_url: str, pygeoapi_reachable: bool) -> str:
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    resp = requests.get(
        f"{pygeoapi_url}/collections/{COLLECTION}/items",
        params={"limit": 1, "f": "json"},
        timeout=30,
    )
    features = resp.json()["features"]
    if not features:
        pytest.skip("no records loaded in this stack")
    return features[0]["id"]


def test_custom_base_is_active(pygeoapi_url: str, pygeoapi_reachable: bool):
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    html = _get(f"{pygeoapi_url}/").text
    assert "/static/img/dataplant-logo.svg" in html
    assert "/static/css/dataplant.css" in html


def test_vendored_static_assets_resolve(pygeoapi_url: str, pygeoapi_reachable: bool):
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    for path in (
        "/static/css/dataplant.css",
        "/static/img/dataplant-logo.svg",
        "/static/img/dataplant-mark.svg",
        "/static/img/pygeoapi.png",
    ):
        resp = requests.get(f"{pygeoapi_url}{path}", timeout=30)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/collections",
        "/collections/arc-records",
        "/collections/arc-records/items",
        "/collections/arc-records/queryables",
        "/conformance",
    ],
)
def test_default_pages_still_render(
    pygeoapi_url: str, pygeoapi_reachable: bool, path: str
):
    """Guards the _base.html block contract. A template we do not override must
    still inherit our chrome and return 200, not an UndefinedError 500."""
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    resp = _get(f"{pygeoapi_url}{path}")
    assert resp.status_code == 200, f"{path} returned {resp.status_code}"


def test_non_overridden_page_keeps_jsonld_injector(
    pygeoapi_url: str, pygeoapi_reachable: bool
):
    """The jsonld block's default is pygeoapi's client-side injector; pages we
    do not override must keep it."""
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    html = _get(f"{pygeoapi_url}/collections").text
    assert "application/ld+json" in html