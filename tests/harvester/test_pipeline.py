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


def _ingest_from(source_uri: str, *, registry, last_activity_at: str = ""):
    """Ingest the same fixture as if it lived at two different namespaces.

    The source_uri must differ per call: namespace is derived from it and is the
    final tiebreaker, so reusing one uri would leave both candidates identical
    and `prefer` would keep the incumbent with an empty suppressed_by.
    """
    return pipeline.ingest_arc(
        FIXTURE,
        conn=None,
        provider="dataplant",
        source_uri=source_uri,
        now_iso="2026-06-22T00:00:00Z",
        validator=pipeline.build_validator(),
        source_etag=last_activity_at,
        registry=registry,
    )


def test_second_mirror_is_suppressed_and_names_the_winner():
    from harvester import dedup

    registry = dedup.CollisionRegistry()
    first = _ingest_from(
        "https://git.nfdi4plants.org/ceplas/ArcPrototype",
        registry=registry, last_activity_at="2026-07-01T00:00:00Z",
    )
    second = _ingest_from(
        "https://git.nfdi4plants.org/muehlhaus/ArcPrototype",
        registry=registry, last_activity_at="2026-01-01T00:00:00Z",
    )

    assert first.suppressed_by == ""
    assert second.suppressed_by == "ceplas", "the more recent mirror is kept"
    assert second.record_id == first.record_id
    # `upsert_ok` cannot carry this signal: conn=None makes it False either way.
    # Assert the resolution itself instead - suppressed, not re-minted.
    assert second.disambiguated_to == "", "a mirror is suppressed, not disambiguated"
    assert registry.winner(first.record_id).namespace == "ceplas"


def test_registry_records_the_title_for_the_report():
    from harvester import dedup

    outcome = _ingest(registry=dedup.CollisionRegistry())
    assert outcome.title != ""


def test_no_registry_preserves_todays_behavior():
    outcome = _ingest()
    assert outcome.suppressed_by == ""
    assert outcome.disambiguated_to == ""
    assert outcome.validate_ok is True


def test_non_mirror_collision_is_disambiguated_not_dropped():
    """Two different datasets sharing an investigation identifier must both survive.

    Pre-seeds the registry with a differently-titled dataset already holding
    ArcPrototype's id. The fixture set has no natural pair like this, so the
    collision is staged directly on the registry rather than via a new fixture.
    """
    import re

    from harvester import dedup

    registry = dedup.CollisionRegistry()

    class _Held:
        suppressed_by = ""
        upsert_ok = True
        disambiguated_to = ""

    registry.resolve(
        dedup.Candidate(
            record_id="dataplant-arcprototype",
            title="Something Completely Different",
            has_doi=True,
            last_activity_at="2026-09-01T00:00:00Z",
            namespace="otherlab",
            unique_id="11111111-1111-1111-1111-111111111111",
        ),
        _Held(),
    )

    outcome = _ingest_from(
        "https://git.nfdi4plants.org/ceplas/ArcPrototype",
        registry=registry, last_activity_at="2026-01-01T00:00:00Z",
    )

    assert outcome.record_id != "dataplant-arcprototype", "must not reuse the held id"
    assert outcome.disambiguated_to == outcome.record_id
    assert outcome.suppressed_by == "", "a non-mirror is kept, not suppressed"
    assert re.fullmatch(r"^[a-z0-9][a-z0-9-]*$", outcome.record_id), "must satisfy the record schema pattern"
    assert len(registry.reviews) == 1, "the pair must be flagged for a human"
