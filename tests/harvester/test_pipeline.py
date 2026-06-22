"""Unit tests for the shared per-ARC pipeline."""
from __future__ import annotations

from pathlib import Path

from harvester import pipeline

FIXTURE = Path(__file__).parent.parent / "fixtures" / "arcs" / "ArcPrototype"


def test_ingest_arc_validate_only_no_conn_builds_valid_record():
    validator = pipeline.build_validator()
    outcome = pipeline.ingest_arc(
        FIXTURE,
        conn=None,
        provider="dataplant",
        source_uri="https://example.org/arc",
        now_iso="2026-06-22T00:00:00Z",
        validator=validator,
    )
    assert outcome.parse_ok is True
    assert outcome.build_ok is True
    assert outcome.validate_ok is True
    assert outcome.validate_errors == []
    assert outcome.record_id == "dataplant-arcprototype"
    assert outcome.upsert_ok is False  # no conn -> no upsert attempted
    assert outcome.n_studies == 2


def test_ingest_arc_parse_failure_is_captured_not_raised(tmp_path):
    validator = pipeline.build_validator()
    # An empty dir is not a valid ARC; arctrl raises -> captured, not propagated.
    outcome = pipeline.ingest_arc(
        tmp_path,
        conn=None,
        provider="dataplant",
        source_uri="file:///nope",
        now_iso="2026-06-22T00:00:00Z",
        validator=validator,
    )
    assert outcome.parse_ok is False
    assert outcome.parse_exc_type != ""
    assert outcome.build_ok is False
