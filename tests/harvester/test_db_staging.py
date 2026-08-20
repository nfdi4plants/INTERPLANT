"""Staging schema, snapshot table, and the search_path guard."""
from __future__ import annotations

import pytest

from harvester import db


@pytest.mark.db
def test_connect_with_schema_routes_writes_to_staging(pg_dsn):
    conn = db.connect(pg_dsn)
    db.apply_schema(conn)
    db.truncate_staging(conn)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM public.records WHERE id = 'staging-probe'")

    staged = db.connect(pg_dsn, schema="staging")
    db.upsert_record(staged, "staging-probe", {"id": "staging-probe"})

    assert db.count_records(staged, schema="staging") == 1
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM public.records WHERE id = 'staging-probe'")
        assert cur.fetchone()[0] == 0


@pytest.mark.db
def test_connect_rejects_a_missing_staging_table(pg_dsn):
    with pytest.raises(RuntimeError, match="nosuchschema.records"):
        db.connect(pg_dsn, schema="nosuchschema")


@pytest.mark.db
def test_published_projects_roundtrip(pg_dsn):
    conn = db.connect(pg_dsn)
    db.apply_schema(conn)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM public.published_projects")
        cur.execute(
            "INSERT INTO public.published_projects (project_path, last_activity_at) "
            "VALUES ('ns/a', '2026-08-01T00:00:00Z'), ('ns/b', '2026-08-02T00:00:00Z')"
        )

    assert db.read_published_projects(conn) == {
        "ns/a": "2026-08-01T00:00:00Z",
        "ns/b": "2026-08-02T00:00:00Z",
    }
    assert db.last_published_at(conn) is not None


@pytest.mark.db
def test_last_published_at_is_none_when_empty(pg_dsn):
    conn = db.connect(pg_dsn)
    db.apply_schema(conn)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM public.published_projects")
    assert db.last_published_at(conn) is None
