"""Smoke tests for the local dev stack."""
from __future__ import annotations

import httpx
import psycopg
import pytest


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


def test_pygeoapi_collections_empty(
    pygeoapi_url: str, pygeoapi_reachable: bool
) -> None:
    """pygeoapi answers /collections with an empty resources list.

    Skipped when pygeoapi is not reachable (e.g. in CI, which does not run
    the pygeoapi service in Plan 2)."""
    if not pygeoapi_reachable:
        pytest.skip(f"pygeoapi not reachable at {pygeoapi_url}")
    response = httpx.get(f"{pygeoapi_url}/collections", timeout=5.0)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "collections" in body, body
    assert body["collections"] == [], body["collections"]
