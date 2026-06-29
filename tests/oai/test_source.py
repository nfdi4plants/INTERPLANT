"""Source layer: datetime granularity parsing/formatting + Postgres queries."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from harvester import batch, db
from harvester.acquire import iter_local_arcs
from oai.source import RecordSource, format_oai_datetime, parse_oai_datetime

FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures" / "arcs"


def test_parse_seconds_granularity():
    assert parse_oai_datetime("2026-06-24T01:02:03Z") == datetime(
        2026, 6, 24, 1, 2, 3, tzinfo=UTC
    )


def test_parse_day_granularity():
    assert parse_oai_datetime("2026-06-24") == datetime(
        2026, 6, 24, 0, 0, 0, tzinfo=UTC
    )


def test_parse_rejects_garbage():
    with pytest.raises(ValueError):
        parse_oai_datetime("not-a-date")


def test_format_is_utc_seconds():
    assert format_oai_datetime(datetime(2026, 6, 24, 1, 2, 3, tzinfo=UTC)) == (
        "2026-06-24T01:02:03Z"
    )


@pytest.fixture
def seeded_dsn(pg_dsn):
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS records CASCADE")
        db.apply_schema(conn)
        batch.run_batch(
            list(iter_local_arcs(FIXTURES_ROOT)),
            conn=conn, now_iso="2026-06-24T00:00:00Z",
            run_timestamp="20260624T000000Z", source="local",
        )
    yield pg_dsn
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS records CASCADE")


@pytest.mark.db
def test_list_returns_all_fixtures(seeded_dsn):
    src = RecordSource(seeded_dsn)
    rows = src.list(limit=100)
    assert len(rows) >= 3
    assert all(r.datestamp.endswith("Z") for r in rows)


@pytest.mark.db
def test_get_known_record(seeded_dsn):
    src = RecordSource(seeded_dsn)
    rec = src.get("dataplant-arcproteomics")
    assert rec is not None
    assert rec.payload["properties"]["title"]


@pytest.mark.db
def test_get_missing_record_returns_none(seeded_dsn):
    assert RecordSource(seeded_dsn).get("nope") is None


@pytest.mark.db
def test_list_paging_cursor_is_exclusive(seeded_dsn):
    src = RecordSource(seeded_dsn)
    first = src.list(limit=1)
    assert len(first) == 1
    rest = src.list(after=(first[0].cursor_ts, first[0].identifier), limit=100)
    assert first[0].identifier not in [r.identifier for r in rest]
