"""Postgres access: schema application + idempotent upsert.

Only this module imports `psycopg`. Callers receive an open connection or
the module can connect from a DSN string.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_VIEWS_PATH = Path(__file__).parent.parent / "sql" / "catalog_views.sql"
_GENERATED_VIEWS_PATH = Path(__file__).parent.parent / "sql" / "catalog_collections.generated.sql"


def connect(dsn: str, *, schema: str | None = None) -> psycopg.Connection:
    """Open an autocommit connection.

    With `schema` set, verify `<schema>.records` exists and put that schema
    first on the search_path, so this module's unqualified DML lands there. The
    verification is the point: with search_path = staging, public, an absent
    staging.records would silently route the harvest into public.records.
    """
    conn = psycopg.connect(dsn, autocommit=True)
    if schema is not None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = 'records'",
                (schema,),
            )
            if cur.fetchone() is None:
                conn.close()
                raise RuntimeError(
                    f"{schema}.records does not exist. Refusing to set search_path: "
                    "unqualified writes would fall through to public.records."
                )
            cur.execute(
                sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema))
            )
    return conn


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


def count_records(conn: psycopg.Connection, *, schema: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT count(*) FROM {}.records").format(sql.Identifier(schema))
        )
        return cur.fetchone()[0]


def truncate_staging(conn: psycopg.Connection) -> None:
    """Clear staged rows so a prior failed run cannot inflate the gate's count."""
    with conn.cursor() as cur:
        cur.execute("TRUNCATE staging.records")


def read_published_projects(conn: psycopg.Connection) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT project_path, last_activity_at FROM public.published_projects")
        return {row[0]: row[1] for row in cur.fetchall()}


def last_published_at(conn: psycopg.Connection) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute("SELECT max(published_at) FROM public.published_projects")
        return cur.fetchone()[0]
