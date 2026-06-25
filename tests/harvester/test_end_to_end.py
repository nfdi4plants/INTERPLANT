"""End-to-end env-gated test: CLI ingest against the ArcPrototype fixture."""
from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from harvester import cli

FIXTURE = Path(__file__).parent.parent / "fixtures" / "arcs" / "ArcPrototype"

pytestmark = pytest.mark.db


@pytest.fixture
def clean_records(pg_dsn: str):
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS records CASCADE")
        yield conn
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS records CASCADE")


def test_ingest_creates_one_row_with_validated_payload(clean_records, pg_dsn) -> None:
    exit_code = cli.main(["ingest", str(FIXTURE), "--dsn", pg_dsn])
    assert exit_code == 0

    with clean_records.cursor() as cur:
        cur.execute("SELECT id, payload FROM records")
        rows = cur.fetchall()

    assert len(rows) == 1
    row_id, payload = rows[0]
    assert row_id == "dataplant-arcprototype"
    # GeoJSON-Feature shape.
    assert payload["type"] == "Feature"
    assert payload["properties"]["title"]
    assert isinstance(payload["properties"]["studies"], list)
    assert len(payload["properties"]["studies"]) == 2


def test_ingest_is_idempotent(clean_records, pg_dsn) -> None:
    assert cli.main(["ingest", str(FIXTURE), "--dsn", pg_dsn]) == 0
    assert cli.main(["ingest", str(FIXTURE), "--dsn", pg_dsn]) == 0
    with clean_records.cursor() as cur:
        cur.execute("SELECT count(*) FROM records")
        (count,) = cur.fetchone()
    assert count == 1
