"""Env-gated Postgres tests for harvester.db.upsert_record."""
from __future__ import annotations

import time

import psycopg
import pytest

from harvester.db import apply_schema, upsert_record

pytestmark = pytest.mark.db


@pytest.fixture
def clean_db(pg_dsn: str):
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS records")
        apply_schema(conn)
        yield conn
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS records")


def test_upsert_inserts_new_row(clean_db) -> None:
    payload = {"id": "dataplant-foo", "title": "Foo"}
    upsert_record(clean_db, "dataplant-foo", payload, source_etag="etag-1")
    with clean_db.cursor() as cur:
        cur.execute("SELECT id, payload, source_etag FROM records")
        rows = cur.fetchall()
    assert len(rows) == 1
    row_id, row_payload, row_etag = rows[0]
    assert row_id == "dataplant-foo"
    assert row_payload == payload
    assert row_etag == "etag-1"


def test_upsert_is_idempotent(clean_db) -> None:
    payload = {"id": "dataplant-foo", "title": "Foo"}
    upsert_record(clean_db, "dataplant-foo", payload, source_etag="etag-1")
    with clean_db.cursor() as cur:
        cur.execute("SELECT ingested_at FROM records")
        (first_ts,) = cur.fetchone()
    time.sleep(0.01)
    upsert_record(clean_db, "dataplant-foo", payload, source_etag="etag-1")
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*), ingested_at FROM records GROUP BY id")
        count, second_ts = cur.fetchone()
    assert count == 1
    assert second_ts > first_ts


def test_upsert_updates_changed_payload(clean_db) -> None:
    upsert_record(clean_db, "dataplant-foo", {"id": "dataplant-foo", "title": "Foo"},
                  source_etag="etag-1")
    upsert_record(clean_db, "dataplant-foo", {"id": "dataplant-foo", "title": "Bar"},
                  source_etag="etag-2")
    with clean_db.cursor() as cur:
        cur.execute("SELECT payload, source_etag FROM records")
        payload, etag = cur.fetchone()
    assert payload["title"] == "Bar"
    assert etag == "etag-2"
