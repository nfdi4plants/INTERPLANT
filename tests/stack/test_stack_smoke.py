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
