"""A successful publish must leave the catalog views in place.

install.sh applies them once, but the nightly refresh is the only thing that
routinely changes this database, so it is where drift would appear. Without
this, public.arc_locations can silently vanish from production and every OGC
locations query 500s until someone runs `make catalog-views` by hand.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from harvester import acquire, batch, cli


class _FakeConn:
    def close(self):
        pass


def test_a_successful_publish_reapplies_the_catalog_views() -> None:
    with patch("harvester.db.apply_catalog_views") as applier:
        _run_refresh_to_successful_publish()
    assert applier.called, (
        "refresh completed a publish without re-applying the catalog views"
    )


def test_an_aborted_publish_does_not_reapply_the_views() -> None:
    with patch("harvester.db.apply_catalog_views") as applier:
        _run_refresh_aborting_at_the_gate()
    assert not applier.called, (
        "views were re-applied even though the publish never swapped"
    )


def _run_refresh_to_successful_publish() -> None:
    rc = _run_refresh()
    assert rc == 0, "refresh did not complete a successful publish"


def _run_refresh_aborting_at_the_gate() -> None:
    rc = _run_refresh(count_records=lambda conn, schema: 3)
    assert rc == 1, "refresh published despite the gate refusing it"


def _run_refresh(*, count_records=None) -> int:
    """Drive cli.refresh to a publish or a gate refusal.

    Same boundary stubs as the `stubbed` fixture in test_cli_refresh.py:
    connect/apply_schema/try_advisory_lock are inert, the batch and audit
    layers report success, and the enumeration holds one changed ARC so the
    diff is non-empty. Override `count_records` to force a gate verdict.
    """
    count = count_records or (lambda conn, schema: 144)
    idents = [
        acquire.ArcIdentity(path="ns/a", web_url="https://g/ns/a", last_activity_at="T1")
    ]

    def fake_iter_live_arcs(base, *, stats=None):
        return iter(idents)

    def fake_swap(conn, *, enumeration):
        return 144

    def fake_batch(identities, **kw):
        list(identities)
        report = batch.BatchReport(source="live", run_timestamp="T")
        report.verdict = "ok"
        return report

    with (
        patch("harvester.db.connect", return_value=_FakeConn()),
        patch("harvester.db.apply_schema"),
        patch("harvester.db.try_advisory_lock", return_value=True),
        patch("harvester.db.truncate_staging"),
        patch("harvester.db.count_records", side_effect=count),
        patch("harvester.db.read_published_projects", return_value={"ns/a": "T0"}),
        patch("harvester.db.last_published_at", return_value=datetime.now(tz=UTC)),
        patch("harvester.acquire.iter_live_arcs", side_effect=fake_iter_live_arcs),
        patch("harvester.audit.write_run_report", return_value=("j.json", "m.md")),
        patch("harvester.audit.aggregate", return_value={"n_upserted": 144}),
        patch("harvester.batch.run_batch", side_effect=fake_batch),
        patch("harvester.publish.swap", side_effect=fake_swap),
    ):
        return cli.main(["refresh", "--dsn", "postgresql://x/y"])