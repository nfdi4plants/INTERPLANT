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
from tests.stack.conftest import RO_PASSWORD

FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures" / "arcs"

ALL_COLLECTIONS = {
    "arc-records",
    "arc-locations",
    "dataplant-proteomics", "dataplant-transcriptomics", "dataplant-genomics",
    "dataplant-metabolomics", "dataplant-phenotyping", "dataplant-imaging",
    "dataplant-microbiome",
}


@pytest.fixture
def seeded(pg_dsn: str, pygeoapi_reachable: bool, pygeoapi_url: str):
    if not pygeoapi_reachable:
        pytest.skip(f"pygeoapi not reachable at {pygeoapi_url}")
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS records CASCADE")
        db.apply_schema(conn)
        batch.run_batch(
            list(iter_local_arcs(FIXTURES_ROOT)),
            conn=conn, now_iso="2026-06-24T00:00:00Z",
            run_timestamp="20260624T000000Z", source="local",
        )
        db.apply_catalog_views(conn)
        # DROP TABLE ... CASCADE took the views and their ACLs with it, so the
        # recreated views start with owner-only privileges. Dev now serves as
        # pygeoapi_ro, exactly like production: re-provision the role the way
        # install.sh does, or every query through the provider 500s.
        db.create_pygeoapi_role(conn, password=RO_PASSWORD)
        db.apply_pygeoapi_role(conn)
    yield


def test_all_collections_present(seeded, pygeoapi_url):
    r = httpx.get(f"{pygeoapi_url}/collections", timeout=5.0)
    assert r.status_code == 200, r.text
    ids = {c["id"] for c in r.json()["collections"]}
    assert ALL_COLLECTIONS <= ids, ids


def test_arc_records_items_serve_with_null_geometry(seeded, pygeoapi_url):
    """A record with no resolvable location must still appear in /items.

    Bbox-filtered views necessarily exclude null-geometry records, so the plain
    listing is the only place the other ~23% of the corpus is reachable. This
    asserts they are present, NOT that every record is null: about 77% of real
    ARCs resolve to a point, and a fixture gains one as soon as its affiliation
    enters harvester/geodata/institutions.json.
    """
    r = httpx.get(f"{pygeoapi_url}/collections/arc-records/items", timeout=5.0)
    assert r.status_code == 200, r.text
    feats = r.json()["features"]
    assert len(feats) >= 3
    # geometry is present as a key on every feature, null or not
    assert all("geometry" in f for f in feats)


def test_no_record_ever_carries_a_polygon_geometry(seeded, pygeoapi_url):
    """Only Point, MultiPoint or null. A bbox Polygon is confidently wrong."""
    r = httpx.get(f"{pygeoapi_url}/collections/arc-records/items", timeout=5.0)
    assert r.status_code == 200, r.text
    kinds = {
        f["geometry"]["type"] for f in r.json()["features"] if f["geometry"] is not None
    }
    assert kinds <= {"Point", "MultiPoint"}, kinds


def test_imaging_collection_is_filtered(seeded, pygeoapi_url):
    r = httpx.get(f"{pygeoapi_url}/collections/dataplant-imaging/items", timeout=5.0)
    assert r.status_code == 200, r.text
    ids = [f["id"] for f in r.json()["features"]]
    assert ids == ["dataplant-arcimaging"]


def test_empty_collection_serves_empty_feature_list(seeded, pygeoapi_url):
    r = httpx.get(f"{pygeoapi_url}/collections/dataplant-genomics/items", timeout=5.0)
    assert r.status_code == 200, r.text
    assert r.json()["features"] == []


def test_queryables_lists_properties(seeded, pygeoapi_url):
    r = httpx.get(f"{pygeoapi_url}/collections/dataplant-proteomics/queryables", timeout=5.0)
    assert r.status_code == 200, r.text
    props = r.json().get("properties", {})
    assert "omics_domains" in props
