"""Unit tests for the batch loop (no DB, no network)."""
from __future__ import annotations

from pathlib import Path

from harvester import batch
from harvester.acquire import ArcIdentity

FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures" / "arcs"


def test_run_batch_local_dry_run_processes_fixtures():
    from harvester.acquire import iter_local_arcs
    identities = list(iter_local_arcs(FIXTURES_ROOT))
    report = batch.run_batch(
        identities,
        conn=None,
        now_iso="2026-06-22T00:00:00Z",
        run_timestamp="20260622T000000Z",
        source="local",
    )
    assert report.verdict == "ok"
    assert len(report.outcomes) == len(identities) >= 1
    proto = next(o for o in report.outcomes if o.path == "ArcPrototype")
    assert proto.parse_ok and proto.build_ok and proto.validate_ok
    assert proto.web_url.startswith("file://")  # identity merged into outcome


def test_run_batch_empty_source_is_failed_verdict():
    report = batch.run_batch(
        [], conn=None, now_iso="2026-06-22T00:00:00Z",
        run_timestamp="20260622T000000Z", source="live",
    )
    assert report.verdict == "failed"
    assert "no arcs" in report.verdict_reason.lower()


def test_run_batch_clone_failure_recorded_and_continues(monkeypatch, tmp_path):
    # A live identity (local_dir=None) whose clone fails must not abort the run.
    monkeypatch.setattr(batch.acquire, "clone_arc", lambda *a, **k: (False, "fatal: nope"))
    ident = ArcIdentity(path="x/bad", web_url="https://g/bad", local_dir=None)
    report = batch.run_batch(
        [ident], conn=None, now_iso="2026-06-22T00:00:00Z",
        run_timestamp="20260622T000000Z", source="live",
    )
    assert report.verdict == "ok"  # ran to completion
    assert report.outcomes[0].clone_ok is False
    assert "nope" in report.outcomes[0].clone_error


def test_batch_dedups_two_namespaces_sharing_one_record_id():
    """The 36-record data loss, in miniature."""
    from harvester import acquire, batch

    fixture = Path(__file__).parent.parent / "fixtures" / "arcs" / "ArcPrototype"
    identities = [
        acquire.ArcIdentity(
            path="ceplas/ArcPrototype",
            web_url="https://git.nfdi4plants.org/ceplas/ArcPrototype",
            last_activity_at="2026-07-01T00:00:00Z",
            local_dir=str(fixture),
        ),
        acquire.ArcIdentity(
            path="muehlhaus/ArcPrototype",
            web_url="https://git.nfdi4plants.org/muehlhaus/ArcPrototype",
            last_activity_at="2026-01-01T00:00:00Z",
            local_dir=str(fixture),
        ),
    ]
    report = batch.run_batch(
        identities, conn=None, now_iso="2026-08-04T00:00:00Z",
        run_timestamp="20260804T000000Z", source="fixtures",
    )
    assert len(report.outcomes) == 2
    suppressed = [o for o in report.outcomes if o.suppressed_by]
    assert len(suppressed) == 1, "one of the two mirrors must be suppressed"
    assert suppressed[0].path == "muehlhaus/ArcPrototype", (
        "ceplas has the more recent last_activity_at, so muehlhaus is suppressed"
    )


def test_batch_filters_template_arcs_when_asked():
    from harvester import acquire, batch

    fixture = Path(__file__).parent.parent / "fixtures" / "arcs" / "ArcPrototype"
    identities = [
        acquire.ArcIdentity(
            path="arc_templates/arc",
            web_url="https://git.nfdi4plants.org/arc_templates/arc",
            local_dir=str(fixture),
        ),
    ]
    report = batch.run_batch(
        identities, conn=None, now_iso="2026-08-04T00:00:00Z",
        run_timestamp="20260804T000000Z", source="fixtures", apply_filters=True,
    )
    assert report.outcomes[0].filtered is True
    assert report.outcomes[0].filter_rule == "template-assays"
