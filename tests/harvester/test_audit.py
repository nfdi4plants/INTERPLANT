"""Unit tests for the audit artifact writer."""
from __future__ import annotations

import json

from harvester import audit
from harvester.batch import BatchReport
from harvester.pipeline import ArcOutcome


def _sample_report() -> BatchReport:
    good = ArcOutcome(
        path="a/good", web_url="https://g/good", clone_ok=True, parse_ok=True,
        build_ok=True, validate_ok=True, upsert_ok=True, record_id="dataplant-good",
        n_studies=1, n_assays=2, omics_classified=2, omics_total=2,
    )
    bad = ArcOutcome(path="a/bad", web_url="https://g/bad", clone_ok=False, clone_error="nope")
    return BatchReport(
        source="live", run_timestamp="20260622T000000Z",
        gitlab_base="https://g", outcomes=[good, bad],
    )


def test_aggregate_counts():
    agg = audit.aggregate(_sample_report())
    assert agg["n_total"] == 2
    assert agg["n_cloned"] == 1
    assert agg["n_parsed"] == 1
    assert agg["n_valid"] == 1
    assert agg["n_upserted"] == 1


def test_write_run_report_emits_json_and_md(tmp_path):
    json_path, md_path = audit.write_run_report(_sample_report(), tmp_path)
    assert json_path.exists() and md_path.exists()
    data = json.loads(json_path.read_text("utf-8"))
    assert data["run_timestamp"] == "20260622T000000Z"
    assert len(data["outcomes"]) == 2
    md = md_path.read_text("utf-8")
    assert "Batch Harvest Report" in md
    assert "a/good" in md
