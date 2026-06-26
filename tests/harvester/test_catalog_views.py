"""DB-backed: catalog views flatten records and filter each omics collection."""
from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from harvester import batch, db
from harvester.acquire import iter_local_arcs

pytestmark = pytest.mark.db

FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures" / "arcs"

# Domains and the fixture ids expected in each (empty list = no fixture data).
EXPECTED = {
    "proteomics": ["dataplant-arcproteomics"],
    "imaging": ["dataplant-arcimaging"],
    "transcriptomics": [],
    "genomics": [],
    "metabolomics": [],
    "phenotyping": [],
    "microbiome": [],
}


def _drop(conn):
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS records CASCADE")


@pytest.fixture
def seeded_conn(pg_dsn: str):
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        _drop(conn)
        db.apply_schema(conn)
        batch.run_batch(
            list(iter_local_arcs(FIXTURES_ROOT)),
            conn=conn, now_iso="2026-06-24T00:00:00Z",
            run_timestamp="20260624T000000Z", source="local",
        )
        db.apply_catalog_views(conn)
        yield conn
        _drop(conn)


def test_arc_records_has_one_row_per_fixture(seeded_conn):
    n_fixtures = len(list(iter_local_arcs(FIXTURES_ROOT)))
    with seeded_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM arc_records")
        (count,) = cur.fetchone()
    assert count == n_fixtures >= 3


def test_geometry_is_null_for_all_rows(seeded_conn):
    with seeded_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM arc_records WHERE geom IS NOT NULL")
        (n,) = cur.fetchone()
    assert n == 0


@pytest.mark.parametrize("domain,expected_ids", sorted(EXPECTED.items()))
def test_domain_view_filters_correctly(seeded_conn, domain, expected_ids):
    with seeded_conn.cursor() as cur:
        cur.execute(f"SELECT id FROM arc_records_{domain} ORDER BY id")
        ids = [r[0] for r in cur.fetchall()]
    assert ids == expected_ids
