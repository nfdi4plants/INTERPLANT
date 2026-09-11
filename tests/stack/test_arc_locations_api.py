"""Tests for the arc-locations OGC API Features collection."""
from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _requires_pygeoapi(pygeoapi_reachable: bool, pygeoapi_url: str):
    if not pygeoapi_reachable:
        pytest.skip(f"pygeoapi not reachable at {pygeoapi_url}")


def test_collection_is_advertised(pygeoapi_url) -> None:
    resp = httpx.get(f"{pygeoapi_url}/collections", params={"f": "json"}, timeout=30)
    resp.raise_for_status()
    ids = {c["id"] for c in resp.json()["collections"]}
    assert "arc-locations" in ids


def test_items_are_point_features(seeded_locations, pygeoapi_url) -> None:
    resp = httpx.get(
        f"{pygeoapi_url}/collections/arc-locations/items",
        params={"f": "json", "limit": 50},
        timeout=30,
    )
    resp.raise_for_status()
    feats = resp.json()["features"]
    assert feats
    assert all(f["geometry"]["type"] == "Point" for f in feats)


def test_role_is_queryable(seeded_locations, pygeoapi_url) -> None:
    resp = httpx.get(
        f"{pygeoapi_url}/collections/arc-locations/items",
        params={"f": "json", "role": "collection-site", "limit": 50},
        timeout=30,
    )
    resp.raise_for_status()
    feats = resp.json()["features"]
    assert feats
    assert all(f["properties"]["role"] == "collection-site" for f in feats)


def test_a_point_carries_its_record_id_for_joining_back(seeded_locations, pygeoapi_url) -> None:
    resp = httpx.get(
        f"{pygeoapi_url}/collections/arc-locations/items",
        params={"f": "json", "limit": 1},
        timeout=30,
    )
    resp.raise_for_status()
    assert "record_id" in resp.json()["features"][0]["properties"]


def test_a_multi_point_record_yields_one_feature_per_point(seeded_locations, pygeoapi_url) -> None:
    """dataplant-multi has 3 location rows; record_id alone is not a unique id,
    so id_field must point at a column that is - otherwise pygeoapi's
    PostgreSQL provider collapses every row sharing a record_id into one.

    Filtered server-side on record_id rather than paging and filtering here:
    this view holds one row per point, so a real corpus puts thousands of rows
    in front of the seeded ones (a single ARC in the live corpus contributes
    387). A client-side filter over the first page passes only while the
    database is nearly empty.
    """
    resp = httpx.get(
        f"{pygeoapi_url}/collections/arc-locations/items",
        params={"f": "json", "record_id": "dataplant-multi", "limit": 100},
        timeout=30,
    )
    resp.raise_for_status()
    ours = resp.json()["features"]
    assert len(ours) == 3
    assert len({f["id"] for f in ours}) == 3


def test_role_filter_returns_every_matching_point(seeded_locations, pygeoapi_url) -> None:
    """dataplant-multi has 2 collection-site points; both must come back, not 1."""
    resp = httpx.get(
        f"{pygeoapi_url}/collections/arc-locations/items",
        params={
            "f": "json",
            "role": "collection-site",
            "record_id": "dataplant-multi",
            "limit": 50,
        },
        timeout=30,
    )
    resp.raise_for_status()
    ours = resp.json()["features"]
    assert len(ours) == 2
