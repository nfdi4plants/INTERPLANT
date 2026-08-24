"""The refresh command's decision logic, with the expensive parts stubbed."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from harvester import acquire, batch, cli


class _FakeConn:
    def close(self):
        pass


@pytest.fixture
def stubbed(monkeypatch):
    """Stub every boundary: GitLab, Postgres, the batch loop, the report writer.

    Patch through `cli.<module>` throughout. `cli.db` is the same module object
    as `harvester.db`, so patching both would be redundant, and importing the
    modules directly just to patch them would trip ruff's unused-import rule.
    """
    calls = {"batch": 0, "swap": 0, "truncate": 0}

    monkeypatch.setattr(cli.db, "connect", lambda dsn, schema=None: _FakeConn())
    monkeypatch.setattr(cli.db, "apply_schema", lambda conn: None)
    monkeypatch.setattr(
        cli.db, "truncate_staging",
        lambda conn: calls.__setitem__("truncate", calls["truncate"] + 1),
    )
    monkeypatch.setattr(cli.db, "count_records", lambda conn, schema: 144)
    monkeypatch.setattr(
        cli.audit, "write_run_report", lambda report, out: ("j.json", "m.md")
    )

    def fake_batch(identities, **kw):
        calls["batch"] += 1
        list(identities)
        report = batch.BatchReport(source="live", run_timestamp="T")
        report.verdict = "ok"
        return report

    monkeypatch.setattr(cli.batch, "run_batch", fake_batch)
    monkeypatch.setattr(cli.audit, "aggregate", lambda report: {"n_upserted": 144})

    def fake_swap(conn, *, enumeration):
        calls["swap"] += 1
        return 144

    monkeypatch.setattr(cli.publish, "swap", fake_swap)
    return calls


def _live(monkeypatch, mapping):
    idents = [
        acquire.ArcIdentity(path=p, web_url=f"https://g/{p}", last_activity_at=t)
        for p, t in mapping.items()
    ]
    monkeypatch.setattr(cli.acquire, "iter_live_arcs", lambda base: iter(idents))


def test_no_change_and_fresh_snapshot_skips_the_harvest(stubbed, monkeypatch):
    _live(monkeypatch, {"ns/a": "T0"})
    monkeypatch.setattr(cli.db, "read_published_projects", lambda conn: {"ns/a": "T0"})
    monkeypatch.setattr(
        cli.db, "last_published_at", lambda conn: datetime.now(tz=UTC)
    )

    assert cli.main(["refresh", "--dsn", "postgresql://x/y"]) == 0
    assert stubbed["batch"] == 0
    assert stubbed["swap"] == 0


def test_a_changed_enumeration_harvests_and_publishes(stubbed, monkeypatch):
    _live(monkeypatch, {"ns/a": "T1"})
    monkeypatch.setattr(cli.db, "read_published_projects", lambda conn: {"ns/a": "T0"})
    monkeypatch.setattr(
        cli.db, "last_published_at", lambda conn: datetime.now(tz=UTC)
    )

    assert cli.main(["refresh", "--dsn", "postgresql://x/y"]) == 0
    assert stubbed["batch"] == 1
    assert stubbed["truncate"] == 1
    assert stubbed["swap"] == 1


def test_a_stale_snapshot_forces_a_harvest_with_no_diff(stubbed, monkeypatch):
    _live(monkeypatch, {"ns/a": "T0"})
    monkeypatch.setattr(cli.db, "read_published_projects", lambda conn: {"ns/a": "T0"})
    monkeypatch.setattr(
        cli.db,
        "last_published_at",
        lambda conn: datetime.now(tz=UTC) - timedelta(days=8),
    )

    assert cli.main(["refresh", "--dsn", "postgresql://x/y"]) == 0
    assert stubbed["batch"] == 1


def test_never_published_forces_a_harvest(stubbed, monkeypatch):
    _live(monkeypatch, {"ns/a": "T0"})
    monkeypatch.setattr(cli.db, "read_published_projects", lambda conn: {})
    monkeypatch.setattr(cli.db, "last_published_at", lambda conn: None)

    assert cli.main(["refresh", "--dsn", "postgresql://x/y"]) == 0
    assert stubbed["batch"] == 1


def test_force_harvests_even_when_nothing_changed(stubbed, monkeypatch):
    _live(monkeypatch, {"ns/a": "T0"})
    monkeypatch.setattr(cli.db, "read_published_projects", lambda conn: {"ns/a": "T0"})
    monkeypatch.setattr(
        cli.db, "last_published_at", lambda conn: datetime.now(tz=UTC)
    )

    assert cli.main(["refresh", "--dsn", "postgresql://x/y", "--force"]) == 0
    assert stubbed["batch"] == 1


def test_the_gate_floor_uses_the_record_count_not_the_project_count(
    stubbed, monkeypatch
):
    """Regression: the snapshot has one entry per project, the corpus one row
    per record. On the real corpus that is 213 vs 144, so comparing the staged
    record count against the project count sets the floor to 191 and refuses
    every publish forever."""
    live = {f"ns/p{i}": "T1" for i in range(213)}
    _live(monkeypatch, live)
    monkeypatch.setattr(
        cli.db, "read_published_projects", lambda conn: {f"ns/p{i}": "T0" for i in range(213)}
    )
    monkeypatch.setattr(cli.db, "last_published_at", lambda conn: datetime.now(tz=UTC))
    # 144 records in both staging and public: a healthy steady state.
    monkeypatch.setattr(cli.db, "count_records", lambda conn, schema: 144)
    monkeypatch.setattr(cli.audit, "aggregate", lambda report: {"n_upserted": 144})

    assert cli.main(["refresh", "--dsn", "postgresql://x/y"]) == 0
    assert stubbed["swap"] == 1, (
        "gate refused a healthy corpus: it is comparing records against projects"
    )


def test_a_refused_gate_does_not_swap(stubbed, monkeypatch):
    _live(monkeypatch, {"ns/a": "T1"})
    monkeypatch.setattr(cli.db, "read_published_projects", lambda conn: {"ns/a": "T0"})
    monkeypatch.setattr(cli.db, "last_published_at", lambda conn: datetime.now(tz=UTC))
    # The database staged fewer rows than the report claims.
    monkeypatch.setattr(cli.db, "count_records", lambda conn, schema: 3)

    assert cli.main(["refresh", "--dsn", "postgresql://x/y"]) == 1
    assert stubbed["swap"] == 0


def test_a_failed_harvest_does_not_swap(stubbed, monkeypatch):
    _live(monkeypatch, {"ns/a": "T1"})
    monkeypatch.setattr(cli.db, "read_published_projects", lambda conn: {"ns/a": "T0"})
    monkeypatch.setattr(cli.db, "last_published_at", lambda conn: datetime.now(tz=UTC))

    def failing_batch(identities, **kw):
        list(identities)
        report = batch.BatchReport(source="live", run_timestamp="T")
        report.verdict = "failed"
        report.verdict_reason = "No ARCs enumerated"
        return report

    monkeypatch.setattr(cli.batch, "run_batch", failing_batch)

    assert cli.main(["refresh", "--dsn", "postgresql://x/y"]) == 1
    assert stubbed["swap"] == 0
