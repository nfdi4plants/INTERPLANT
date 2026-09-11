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
_PYGEOAPI_ROLE_PATH = Path(__file__).parent.parent / "sql" / "pygeoapi_role.sql"

# Fixed advisory lock key serializing the refresh pipeline. Arbitrary but
# must never change once deployed: it is only meaningful as long as every
# refresh run agrees on the same number. Two overlapping refresh runs would
# otherwise share one staging table and compute the mirror-dedup winner
# against a partial candidate set.
REFRESH_LOCK_KEY = 561_073_442


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
    ddl = _SCHEMA_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(ddl)


def apply_catalog_views(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(_VIEWS_PATH.read_text(encoding="utf-8"))
        cur.execute(_GENERATED_VIEWS_PATH.read_text(encoding="utf-8"))


def apply_pygeoapi_role(conn: psycopg.Connection, *, password: str) -> None:
    """Create or update the read-only role pygeoapi connects as.

    The password is set separately from the DDL so the SQL file stays free of
    credentials and can be read in a diff. Idempotent: safe to re-run on every
    install, which is how the role picks up a rotated password. CONNECT is
    granted on the database the caller is connected to, not a hardcoded name.
    """
    with conn.cursor() as cur:
        cur.execute(_PYGEOAPI_ROLE_PATH.read_text(encoding="utf-8"))
        cur.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO pygeoapi_ro").format(
                sql.Identifier(conn.info.dbname)
            )
        )
        cur.execute(
            sql.SQL("ALTER ROLE pygeoapi_ro WITH PASSWORD {}").format(sql.Literal(password))
        )


def upsert_record(
    conn: psycopg.Connection,
    record_id: str,
    payload: dict[str, Any],
    *,
    source_etag: str | None = None,
) -> None:
    stmt = """
        INSERT INTO records (id, payload, source_etag, ingested_at)
        VALUES (%(id)s, %(payload)s, %(etag)s, now())
        ON CONFLICT (id) DO UPDATE
          SET payload     = EXCLUDED.payload,
              source_etag = EXCLUDED.source_etag,
              ingested_at = now()
    """
    with conn.cursor() as cur:
        cur.execute(
            stmt,
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


def try_advisory_lock(conn: psycopg.Connection) -> bool:
    """Attempt the session-level refresh lock; returns whether it was acquired.

    A session-level advisory lock is tied to the connection, not the
    transaction, so it survives autocommit and is released automatically
    when the connection closes or the process dies - it cannot wedge the
    nightly timer if a run is killed.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", (REFRESH_LOCK_KEY,))
        return cur.fetchone()[0]
