"""catalog_views.sql must re-apply cleanly over an existing database.

`apply_catalog_views` (and `deploy/install.sh` behind it) runs this file
against a database that already holds the previous revision of the views.
PostgreSQL's CREATE OR REPLACE VIEW is far more restrictive than it looks: it
can APPEND columns, but it cannot insert one mid-list, reorder them, rename
one, or change a type. Any of those fails with

    ERROR: cannot change name of view column "role" to "created"

which aborts the deployment. The failure never shows up in a fresh dev stack,
where the view is created rather than replaced - only against production.

So this test applies the file twice and asserts the second run succeeds.
"""
from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

VIEWS_SQL = Path(__file__).resolve().parents[2] / "sql" / "catalog_views.sql"
GENERATED_SQL = (
    Path(__file__).resolve().parents[2] / "sql" / "catalog_collections.generated.sql"
)


def _apply(dsn: str, sql: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql)


def test_catalog_views_re_apply_over_themselves(pg_dsn: str):
    sql = VIEWS_SQL.read_text(encoding="utf-8")
    _apply(pg_dsn, sql)
    try:
        _apply(pg_dsn, sql)
    except psycopg.errors.InvalidTableDefinition as exc:
        pytest.fail(
            "catalog_views.sql cannot replace the views it just created, so "
            "applying it to production will abort. New columns must be "
            "APPENDED to the end of the select list, never inserted or "
            f"renamed. PostgreSQL said: {exc}"
        )


def test_generated_collection_views_re_apply_over_themselves(pg_dsn: str):
    # The per-domain views depend on arc_records, so they are replaced in the
    # same deployment step and carry the same constraint.
    _apply(pg_dsn, VIEWS_SQL.read_text(encoding="utf-8"))
    sql = GENERATED_SQL.read_text(encoding="utf-8")
    _apply(pg_dsn, sql)
    try:
        _apply(pg_dsn, sql)
    except psycopg.errors.InvalidTableDefinition as exc:
        pytest.fail(f"catalog_collections.generated.sql is not re-appliable: {exc}")
