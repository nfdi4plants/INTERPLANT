"""Deterministic batch gate: all pinned fixture ARCs must parse/build/validate/upsert."""
from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from harvester import batch
from harvester.acquire import iter_local_arcs

pytestmark = pytest.mark.db

FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures" / "arcs"


@pytest.fixture
def clean_conn(pg_dsn: str):
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS records CASCADE")
        from harvester import db
        db.apply_schema(conn)
        yield conn
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS records CASCADE")


def _run(conn):
    return batch.run_batch(
        list(iter_local_arcs(FIXTURES_ROOT)),
        conn=conn, now_iso="2026-06-22T00:00:00Z",
        run_timestamp="20260622T000000Z", source="local",
    )


def test_all_fixtures_pass_the_full_pipeline(clean_conn):
    report = _run(clean_conn)
    assert report.verdict == "ok"
    assert len(report.outcomes) >= 3
    for o in report.outcomes:
        assert o.parse_ok and o.build_ok and o.validate_ok and o.upsert_ok, o.path


def test_fixture_harvest_is_idempotent(clean_conn):
    _run(clean_conn)
    _run(clean_conn)
    with clean_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM records")
        (count,) = cur.fetchone()
    # One row per distinct fixture ARC; a second run upserts, not inserts.
    assert count == len(list(iter_local_arcs(FIXTURES_ROOT)))
