"""Gating + fixtures for OAI service tests.

Pure tests (no DB) always run. Tests marked `db` need Postgres (INTERPLANT_STACK_TESTS=1).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

_STACK_GATE = "INTERPLANT_STACK_TESTS"
_DEFAULT_DSN = "postgresql://interplant:interplant@localhost:5432/interplant"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get(_STACK_GATE) == "1":
        return
    skip_db = pytest.mark.skip(reason=f"set {_STACK_GATE}=1 to enable db-backed tests")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)


@pytest.fixture
def pg_dsn() -> str:
    return os.environ.get("INTERPLANT_PG_DSN", _DEFAULT_DSN)


def _utc(y, mo, d, h=0, mi=0, s=0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


@dataclass
class FakeSource:
    """In-memory RecordSource stand-in for pure (no-DB) verb/compliance tests."""
    records: list  # list[oai.source.OaiRecord]

    def earliest_datestamp(self):
        from oai.source import format_oai_datetime
        if not self.records:
            return None
        return format_oai_datetime(min(r.cursor_ts for r in self.records))

    def get(self, identifier):
        return next((r for r in self.records if r.identifier == identifier), None)

    def list(self, *, frm=None, until=None, after=None, limit=100):
        rows = sorted(self.records, key=lambda r: (r.cursor_ts, r.identifier))
        if frm is not None:
            rows = [r for r in rows if r.cursor_ts >= frm]
        if until is not None:
            rows = [r for r in rows if r.cursor_ts <= until]
        if after is not None:
            rows = [r for r in rows if (r.cursor_ts, r.identifier) > after]
        return rows[:limit]


@pytest.fixture
def make_record():
    from oai.source import OaiRecord, format_oai_datetime

    def _make(identifier: str, ts: datetime, payload: dict | None = None) -> OaiRecord:
        return OaiRecord(
            identifier=identifier,
            datestamp=format_oai_datetime(ts),
            cursor_ts=ts,
            payload=payload or _MINIMAL_PAYLOAD(identifier),
        )

    return _make


def _MINIMAL_PAYLOAD(identifier: str) -> dict:
    return {
        "id": identifier,
        "type": "Feature",
        "geometry": None,
        "time": {"interval": [None, None]},
        "properties": {
            "title": f"Title {identifier}",
            "description": "desc",
            "created": "2026-06-24T00:00:00Z",
            "uniqueId": "00000000-0000-5000-8000-000000000000",
            "harvester_version": "0.1.0",
            "arc_source_uri": f"https://example.org/{identifier}",
            "experiment_context": "lab",
            "record_quality": "partial",
            "harvested_at": "2026-06-24T00:00:00Z",
            "keywords": ["alpha"],
            "omics_domains": ["proteomics"],
            "organism": [],
            "project": [],
            "contacts": [],
            "creators": [],
            "publications": [],
            "assays": [],
            "studies": [],
            "location_status": "absent",
            "locations": [],
        },
    }
