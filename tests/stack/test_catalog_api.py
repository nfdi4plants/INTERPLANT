"""OGC API - Records contract tests for the catalog skeleton.

Requires a running pygeoapi configured with arc-records + dataplant-proteomics
(`make catalog-up && make restart`). Skips when pygeoapi is unreachable (CI)."""
from __future__ import annotations

from pathlib import Path

import httpx
import psycopg
import pytest

from harvester import batch, db
from harvester.acquire import iter_local_arcs

FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures" / "arcs"


@pytest.fixture
def seeded(pg_dsn: str, pygeoapi_reachable: bool, pygeoapi_url: str):
    if not pygeoapi_reachable:
        pytest.skip(f"pygeoapi not reachable at {pygeoapi_url}")
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP VIEW IF EXISTS arc_records_proteomics")
            cur.execute("DROP VIEW IF EXISTS arc_records")
            cur.execute("DROP TABLE IF EXISTS records")
        db.apply_schema(conn)
        batch.run_batch(
            list(iter_local_arcs(FIXTURES_ROOT)),
            conn=conn, now_iso="2026-06-24T00:00:00Z",
            run_timestamp="20260624T000000Z", source="local",
        )
        db.apply_catalog_views(conn)
    yield


def test_arc_records_items_serve_with_null_geometry(seeded, pygeoapi_url):
    r = httpx.get(f"{pygeoapi_url}/collections/arc-records/items", timeout=5.0)
    assert r.status_code == 200, r.text
    feats = r.json()["features"]
    assert len(feats) >= 3
    assert all(f["geometry"] is None for f in feats)


def test_proteomics_collection_is_filtered(seeded, pygeoapi_url):
    r = httpx.get(f"{pygeoapi_url}/collections/dataplant-proteomics/items", timeout=5.0)
    assert r.status_code == 200, r.text
    ids = [f["id"] for f in r.json()["features"]]
    assert ids == ["dataplant-arcproteomics"]


def test_queryables_lists_properties(seeded, pygeoapi_url):
    r = httpx.get(f"{pygeoapi_url}/collections/arc-records/queryables", timeout=5.0)
    assert r.status_code == 200, r.text
    props = r.json().get("properties", {})
    assert "omics_domains" in props
    assert "experiment_context" in props


def test_conformance_advertises_records(seeded, pygeoapi_url):
    r = httpx.get(f"{pygeoapi_url}/conformance", timeout=5.0)
    assert r.status_code == 200, r.text
    classes = " ".join(r.json().get("conformsTo", []))
    assert "ogcapi-records" in classes or "cat/1.0" in classes
