"""Postgres access: schema application + idempotent upsert.

Only this module imports `psycopg`. Callers receive an open connection or
the module can connect from a DSN string.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_VIEWS_PATH = Path(__file__).parent.parent / "sql" / "catalog_views.sql"
_GENERATED_VIEWS_PATH = Path(__file__).parent.parent / "sql" / "catalog_collections.generated.sql"


def connect(dsn: str) -> psycopg.Connection:
    return psycopg.connect(dsn, autocommit=True)


def apply_schema(conn: psycopg.Connection) -> None:
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)


def apply_catalog_views(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(_VIEWS_PATH.read_text(encoding="utf-8"))
        cur.execute(_GENERATED_VIEWS_PATH.read_text(encoding="utf-8"))


def upsert_record(
    conn: psycopg.Connection,
    record_id: str,
    payload: dict[str, Any],
    *,
    source_etag: str | None = None,
) -> None:
    sql = """
        INSERT INTO records (id, payload, source_etag, ingested_at)
        VALUES (%(id)s, %(payload)s, %(etag)s, now())
        ON CONFLICT (id) DO UPDATE
          SET payload     = EXCLUDED.payload,
              source_etag = EXCLUDED.source_etag,
              ingested_at = now()
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            {"id": record_id, "payload": Jsonb(payload), "etag": source_etag},
        )
