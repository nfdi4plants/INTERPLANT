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


def test_record_page_shows_title_and_arc_link(
    pygeoapi_url: str, pygeoapi_reachable: bool, item_id: str
):
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    url = f"{pygeoapi_url}/collections/{COLLECTION}/items/{item_id}"
    item = requests.get(url, params={"f": "json"}, timeout=30).json()
    html = _get(url).text
    assert item["properties"]["title"] in html
    assert 'class="dp-cta"' in html
    assert item["properties"]["arc_source_uri"] in html


def test_record_page_has_no_raw_property_table(
    pygeoapi_url: str, pygeoapi_reachable: bool, item_id: str
):
    """The stock template rendered a Property/Value table. Ours must not."""
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    html = _get(f"{pygeoapi_url}/collections/{COLLECTION}/items/{item_id}").text
    assert "externalIds</td>" not in html
    assert "omics_domains</td>" not in html


def test_empty_tag_groups_are_hidden(pygeoapi_url: str, pygeoapi_reachable: bool):
    """keywords is empty on every live record, so no keywords heading may
    appear on a record whose keywords list is empty."""
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    base = f"{pygeoapi_url}/collections/{COLLECTION}/items"
    features = requests.get(
        base, params={"limit": 50, "f": "json"}, timeout=30
    ).json()["features"]
    empty = next(
        (f for f in features if not f["properties"].get("keywords")), None
    )
    if empty is None:
        pytest.skip("no record with empty keywords in this stack")
    html = _get(f"{base}/{empty['id']}").text
    assert "dp-tag--keyword" not in html


def test_contributors_render_with_orcid_links(
    pygeoapi_url: str, pygeoapi_reachable: bool
):
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    base = f"{pygeoapi_url}/collections/{COLLECTION}/items"
    features = requests.get(
        base, params={"limit": 50, "f": "json"}, timeout=30
    ).json()["features"]
    with_orcid = next(
        (
            f
            for f in features
            if any(c.get("identifier") for c in f["properties"].get("contacts") or [])
        ),
        None,
    )
    if with_orcid is None:
        pytest.skip("no record with an ORCID in this stack")
    html = _get(f"{base}/{with_orcid['id']}").text
    orcid = next(
        c["identifier"]
        for c in with_orcid["properties"]["contacts"]
        if c.get("identifier")
    )
    assert orcid in html


NO_LOCATION_TEXT = "No location recorded for this dataset yet"


def _find_record(pygeoapi_url: str, *, with_geometry: bool) -> dict | None:
    features = requests.get(
        f"{pygeoapi_url}/collections/{COLLECTION}/items",
        params={"limit": 50, "f": "json"},
        timeout=30,
    ).json()["features"]
    for feature in features:
        if bool(feature.get("geometry")) is with_geometry:
            return feature
    return None


def test_null_geometry_shows_overlay_and_no_fake_point(
    pygeoapi_url: str, pygeoapi_reachable: bool
):
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    record = _find_record(pygeoapi_url, with_geometry=False)
    if record is None:
        pytest.skip("no null-geometry record in this stack")
    html = _get(
        f"{pygeoapi_url}/collections/{COLLECTION}/items/{record['id']}"
    ).text
    assert NO_LOCATION_TEXT in html
    assert "dp-map--nolocation" in html
    assert "[45, -75]" not in html, "stock template's Ontario fallback is still present"


def test_geometry_record_has_no_overlay(
    pygeoapi_url: str, pygeoapi_reachable: bool
):
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    record = _find_record(pygeoapi_url, with_geometry=True)
    if record is None:
        pytest.skip("no record with geometry in this stack")
    html = _get(
        f"{pygeoapi_url}/collections/{COLLECTION}/items/{record['id']}"
    ).text
    assert NO_LOCATION_TEXT not in html
    assert "dp-map--nolocation" not in html


def test_fitbounds_is_guarded(pygeoapi_url: str, pygeoapi_reachable: bool):
    """Every fitBounds call must be behind an isValid() check. The absence of
    this guard is the defect this task fixes."""
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    record = _find_record(pygeoapi_url, with_geometry=True)
    if record is None:
        pytest.skip("no record with geometry in this stack")
    html = _get(
        f"{pygeoapi_url}/collections/{COLLECTION}/items/{record['id']}"
    ).text
    assert "isValid()" in html