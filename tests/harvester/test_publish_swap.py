"""The staging-to-public swap: atomic, pruning, and snapshot-consistent."""
from __future__ import annotations

import psycopg
import pytest

from harvester import db, publish


def _reset(conn):
    with conn.cursor() as cur:
        cur.execute("TRUNCATE public.records")
        cur.execute("TRUNCATE staging.records")
        cur.execute("TRUNCATE public.published_projects")


@pytest.mark.db
def test_swap_replaces_public_records_and_prunes(pg_dsn):
    conn = db.connect(pg_dsn)
    db.apply_schema(conn)
    _reset(conn)
    with conn.cursor() as cur:
        # An orphan from a previous run: present in public, absent from staging.
        cur.execute(
            "INSERT INTO public.records (id, payload) VALUES ('gone', '{}'::jsonb)"
        )
        cur.execute(
            "INSERT INTO staging.records (id, payload) VALUES "
            "('keep-a', '{}'::jsonb), ('keep-b', '{}'::jsonb)"
        )

    published = publish.swap(conn, enumeration={"ns/keep": "2026-08-20T00:00:00Z"})

    assert published == 2
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM public.records ORDER BY id")
        assert [r[0] for r in cur.fetchall()] == ["keep-a", "keep-b"]
    assert db.read_published_projects(conn) == {"ns/keep": "2026-08-20T00:00:00Z"}


@pytest.mark.db
def test_swap_replaces_rather_than_merges_the_snapshot(pg_dsn):
    conn = db.connect(pg_dsn)
    db.apply_schema(conn)
    _reset(conn)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO public.published_projects (project_path, last_activity_at) "
            "VALUES ('ns/vanished', '2026-01-01T00:00:00Z')"
        )
        cur.execute("INSERT INTO staging.records (id, payload) VALUES ('r', '{}'::jsonb)")

    publish.swap(conn, enumeration={"ns/current": "2026-08-20T00:00:00Z"})

    # A project that disappeared upstream must leave the snapshot, or the
    # detector would report it vanished on every subsequent night.
    assert db.read_published_projects(conn) == {"ns/current": "2026-08-20T00:00:00Z"}


@pytest.mark.db
def test_a_failed_swap_leaves_public_records_untouched(pg_dsn, monkeypatch):
    conn = db.connect(pg_dsn)
    db.apply_schema(conn)
    _reset(conn)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO public.records (id, payload) VALUES ('old', '{}'::jsonb)")
        cur.execute("INSERT INTO staging.records (id, payload) VALUES ('new', '{}'::jsonb)")

    with pytest.raises(psycopg.errors.NotNullViolation):
        # The None value violates published_projects.last_activity_at NOT NULL,
        # aborting the transaction after public.records was already truncated
        # inside it. Typed dict[str, str] deliberately: the violation is the point.
        publish.swap(conn, enumeration={"ns/bad": None})

    with conn.cursor() as cur:
        cur.execute("SELECT id FROM public.records ORDER BY id")
        assert [r[0] for r in cur.fetchall()] == ["old"]
        # The session must survive the abort: a poisoned connection would break
        # the next nightly run.
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1
        # The rollback must be whole, not partial: staging is untouched.
        cur.execute("SELECT id FROM staging.records ORDER BY id")
        assert [r[0] for r in cur.fetchall()] == ["new"]
