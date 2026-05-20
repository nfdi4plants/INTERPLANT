"""Smoke tests for the local dev stack."""
from __future__ import annotations

import psycopg


def test_postgres_reachable(pg_dsn: str) -> None:
    """Postgres 17 answers on the DSN."""
    with psycopg.connect(pg_dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            row = cur.fetchone()
    assert row is not None
    assert row[0].startswith("PostgreSQL 17"), row[0]


def test_postgis_extension_available(pg_dsn: str) -> None:
    """PostGIS 3.6 extension can be created and reports its version."""
    with psycopg.connect(pg_dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
            cur.execute("SELECT postgis_version();")
            row = cur.fetchone()
            conn.rollback()
    assert row is not None
    assert row[0].strip().startswith("3.6"), row[0]
