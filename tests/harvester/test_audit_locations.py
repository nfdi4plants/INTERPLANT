"""Tests for location coverage counts in the run audit."""
from __future__ import annotations

from dataclasses import dataclass, field

from harvester.audit import aggregate


@dataclass
class _Outcome:
    clone_ok: bool = True
    parse_ok: bool = True
    build_ok: bool = True
    validate_ok: bool = True
    filtered: bool = False
    suppressed_by: str | None = None
    upsert_ok: bool = True
    omics_classified: int = 0
    omics_total: int = 0
    location_status: str = "absent"


@dataclass
class _Report:
    outcomes: list = field(default_factory=list)


def test_aggregate_counts_every_location_tier() -> None:
    report = _Report(outcomes=[
        _Outcome(location_status="extracted"),
        _Outcome(location_status="extracted"),
        _Outcome(location_status="geocoded"),
        _Outcome(location_status="institution"),
        _Outcome(location_status="absent"),
    ])
    counts = aggregate(report)["location_status_counts"]
    assert counts == {
        "extracted": 2, "geocoded": 1, "institution": 1, "absent": 1
    }


def test_all_tiers_are_present_even_at_zero() -> None:
    # A stable key set keeps the JSON artifact diffable between runs.
    counts = aggregate(_Report(outcomes=[_Outcome()]))["location_status_counts"]
    assert set(counts) == {"extracted", "geocoded", "institution", "absent"}