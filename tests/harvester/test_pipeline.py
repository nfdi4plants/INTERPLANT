"""Unit tests for the shared per-ARC pipeline."""
from __future__ import annotations

from pathlib import Path

import pytest

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


def _ingest(**kwargs):
    return pipeline.ingest_arc(
        FIXTURE,
        conn=None,
        provider="dataplant",
        source_uri="https://example.org/arc",
        now_iso="2026-06-22T00:00:00Z",
        validator=pipeline.build_validator(),
        **kwargs,
    )


def test_unmet_parse_budget_is_reported_as_parse_timeout():
    """A budget arctrl cannot meet degrades to a recorded failure, not a stall.

    Runs the real arctrl path deliberately: arctrl catches our ParseTimeout and
    re-raises a generic "Could not load ARC" error, so this pins the behaviour we
    depend on to keep timeouts distinct from malformed data in the audit report.
    """
    outcome = _ingest(parse_timeout=0.01)
    assert outcome.parse_ok is False
    assert outcome.parse_exc_type == "ParseTimeout"
    assert outcome.build_ok is False
    assert outcome.upsert_ok is False
    assert outcome.record_id == ""


@pytest.mark.parametrize("disabled", [None, 0])
def test_disabled_parse_budget_still_ingests(disabled):
    """The opt-in default must never drop a slow-but-valid ARC."""
    outcome = _ingest(parse_timeout=disabled)
    assert outcome.parse_ok is True
    assert outcome.validate_ok is True


def test_generous_parse_budget_does_not_interfere():
    outcome = _ingest(parse_timeout=120)
    assert outcome.parse_ok is True
    assert outcome.validate_ok is True
    assert outcome.record_id == "dataplant-arcprototype"


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


IMAGING = Path(__file__).parent.parent / "fixtures" / "arcs" / "ArcImaging"


def test_filters_off_by_default_keeps_the_template_shaped_prototype():
    """ArcPrototype's assays are measurement1/2, so this pins the opt-in default."""
    outcome = _ingest()
    assert outcome.filtered is False
    assert outcome.build_ok is True


def test_template_arc_is_filtered_when_filters_are_enabled():
    outcome = _ingest(apply_filters=True)
    assert outcome.filtered is True
    assert outcome.filter_rule == "template-assays"
    assert outcome.parse_ok is True, "policy exclusion is not a parse failure"
    assert outcome.build_ok is False
    assert outcome.record_id == ""


def test_real_arc_survives_the_filter():
    outcome = pipeline.ingest_arc(
        IMAGING,
        conn=None,
        provider="dataplant",
        source_uri="https://example.org/arc",
        now_iso="2026-06-22T00:00:00Z",
        validator=pipeline.build_validator(),
        apply_filters=True,
    )
    assert outcome.filtered is False
    assert outcome.build_ok is True
