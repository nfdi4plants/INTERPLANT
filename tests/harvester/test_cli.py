"""Unit tests for the harvester CLI orchestrator (DB mocked out)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harvester import cli
from harvester.isa_reader import Assay, Contact, Investigation, Study

FIXTURE = Path(__file__).parent.parent / "fixtures" / "arcs" / "ArcPrototype"


@pytest.fixture
def fake_investigation() -> Investigation:
    return Investigation(
        identifier="ArcPrototype",
        title="Prototype ARC",
        description=None,
        dois=[],
        contacts=[Contact(first_name="A", last_name="B", email=None, orcid=None, affiliation=None)],
        studies=[
            Study(
                identifier="s1",
                title=None,
                assays=[Assay(name="RNA-Seq", folder="RNA-Seq", measurement_type=None)],
            )
        ],
    )


def test_cli_ingest_invokes_upsert_with_built_record(monkeypatch, fake_investigation):
    captured: dict[str, object] = {}

    def fake_read(self, path):
        captured["arc_path"] = Path(path)
        return fake_investigation

    fake_conn = MagicMock()

    def fake_upsert(conn, record_id, payload, *, source_etag=None):
        captured["record_id"] = record_id
        captured["payload"] = payload
        captured["conn"] = conn

    monkeypatch.setattr("harvester.isa_reader.IsaReader.read", fake_read)
    monkeypatch.setattr("harvester.cli.db.connect", lambda dsn: fake_conn)
    monkeypatch.setattr("harvester.cli.db.apply_schema", lambda conn: None)
    monkeypatch.setattr("harvester.pipeline.db.upsert_record", fake_upsert)

    exit_code = cli.main(["ingest", str(FIXTURE), "--dsn", "postgresql://fake"])
    assert exit_code == 0
    assert captured["arc_path"] == FIXTURE
    assert captured["record_id"] == "dataplant-arcprototype"
    # Schema is GeoJSON Feature; omics lives under properties.
    assert captured["payload"]["properties"]["omics_domains"] == ["transcriptomics"]
    # Top-level shape sanity.
    assert captured["payload"]["type"] == "Feature"
    assert captured["payload"]["id"] == "dataplant-arcprototype"


def test_cli_missing_path_returns_nonzero():
    exit_code = cli.main(["ingest", "/no/such/path", "--dsn", "postgresql://fake"])
    assert exit_code != 0


def test_cli_no_command_returns_nonzero():
    exit_code = cli.main([])
    assert exit_code != 0


def test_cli_harvest_local_dry_run_writes_report(tmp_path):
    fixtures_root = FIXTURE.parent  # tests/fixtures/arcs
    exit_code = cli.main([
        "harvest", "--local-dir", str(fixtures_root),
        "--dry-run", "--out-dir", str(tmp_path),
    ])
    assert exit_code == 0
    reports = list(tmp_path.glob("harvest-*.json"))
    assert len(reports) == 1


def test_cli_harvest_rejects_dry_run_with_dsn():
    exit_code = cli.main([
        "harvest", "--local-dir", "x", "--dry-run", "--dsn", "postgresql://fake",
    ])
    assert exit_code == 2


def test_cli_harvest_missing_local_dir_returns_nonzero():
    exit_code = cli.main([
        "harvest", "--local-dir", "/no/such/dir", "--dry-run",
    ])
    assert exit_code != 0


@pytest.mark.live
def test_cli_harvest_live_smoke(tmp_path):
    """Gated by INTERPLANT_LIVE_HARVEST=1; hits git.nfdi4plants.org."""
    exit_code = cli.main([
        "harvest", "--source", "live", "--dry-run", "--limit", "3",
        "--out-dir", str(tmp_path),
    ])
    assert exit_code == 0
    assert list(tmp_path.glob("harvest-*.json"))
