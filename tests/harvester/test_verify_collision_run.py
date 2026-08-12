"""Unit tests for scripts/verify_collision_run.py.

The script is the gate we read a full-corpus harvest through, so its two load
bearing behaviours - one terminal state per ARC, and detecting an id claimed by
two ARCs - are worth pinning. A checker that silently passes a broken run is
worse than no checker.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import verify_collision_run as vcr  # noqa: E402


def _outcome(path: str, **overrides) -> dict:
    base = {
        "path": path,
        "web_url": f"https://git.nfdi4plants.org/{path}",
        "clone_ok": True,
        "parse_ok": True,
        "build_ok": True,
        "validate_ok": True,
        "upsert_ok": False,
        "filtered": False,
        "filter_rule": "",
        "record_id": "dataplant-x",
        "suppressed_by": "",
        "disambiguated_to": "",
        "title": "A title",
        "last_activity_at": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def _data(outcomes: list[dict]) -> dict:
    return {
        "run_timestamp": "20260812T000000Z",
        "source": "live",
        "outcomes": outcomes,
        "totals": {
            "n_total": len(outcomes),
            "n_upserted": 0,
            "omics_classified": 0,
            "omics_total": 0,
        },
    }


def test_terminal_state_picks_the_earliest_failure():
    # A clone failure is reported even though the later flags are also false.
    assert vcr.terminal_state(_outcome("a/b", clone_ok=False, parse_ok=False)) == "clone_failed"
    assert vcr.terminal_state(_outcome("a/b", parse_ok=False)) == "parse_failed"
    assert vcr.terminal_state(_outcome("a/b", build_ok=False)) == "build_failed"
    assert vcr.terminal_state(_outcome("a/b", validate_ok=False)) == "validation_failed"


def test_filtered_outranks_parse_state():
    """Exclusion is a policy decision, not a data failure - it must not be
    reported as a parse failure just because parsing never ran."""
    rec = _outcome("a/b", filtered=True, filter_rule="placeholder-identifier", parse_ok=False)
    assert vcr.terminal_state(rec) == "filtered"


def test_suppressed_and_would_write_are_distinct():
    assert vcr.terminal_state(_outcome("a/b", suppressed_by="ceplas")) == "suppressed"
    assert vcr.terminal_state(_outcome("a/b")) == "would_write"


def test_clean_run_reconciles(capsys):
    data = _data([
        _outcome("ceplas/one", record_id="dataplant-one"),
        _outcome("x/two", record_id="dataplant-two"),
        _outcome("y/three", record_id="dataplant-one", suppressed_by="ceplas"),
    ])
    assert vcr.report(data) == 0
    assert "Funnel reconciles" in capsys.readouterr().out


def test_two_arcs_writing_one_id_fails_the_run(capsys):
    """The exact defect the collision fix exists to prevent."""
    data = _data([
        _outcome("ceplas/one", record_id="dataplant-dup"),
        _outcome("other/one", record_id="dataplant-dup"),
    ])
    assert vcr.report(data) == 1
    out = capsys.readouterr().out
    assert "POLICY FAILURE" in out
    assert "FAILED" in out


def test_missing_outcome_rows_fail_the_run(capsys):
    data = _data([_outcome("a/b")])
    data["totals"]["n_total"] = 5  # report claims 5 ARCs, carries 1
    assert vcr.report(data) == 1
    assert "unaccounted for" in capsys.readouterr().out


def test_unique_exclusion_is_flagged_as_outright_data_loss(capsys):
    """An excluded ARC in no collision group is dropped, not deduplicated."""
    data = _data([
        _outcome("perelo/samplearc_nfcore", filtered=True,
                 filter_rule="placeholder-identifier",
                 record_id="dataplant-samplearc-nfcore"),
        _outcome("other/real", record_id="dataplant-real"),
    ])
    vcr.report(data)
    assert "no - unique record" in capsys.readouterr().out


def test_disambiguated_group_still_reports_as_one_collision(capsys):
    """A split group must stay visible: grouping on the suffixed id would hide
    the collision the split came from."""
    data = _data([
        _outcome("ceplas/cplantbox", record_id="dataplant-cplantbox"),
        _outcome("x.zhou/model", record_id="dataplant-cplantbox-ab12cd",
                 disambiguated_to="dataplant-cplantbox-ab12cd"),
    ])
    groups = vcr._collision_groups(data["outcomes"])
    assert list(groups) == ["dataplant-cplantbox"]
    assert vcr.report(data) == 0
    assert "Held apart by the title guard" in capsys.readouterr().out


def test_same_namespace_group_is_reported_as_needing_the_tiebreak(capsys):
    data = _data([
        _outcome("ns/one", web_url="https://git.nfdi4plants.org/ns/one",
                 record_id="dataplant-tie"),
        _outcome("ns/two", web_url="https://git.nfdi4plants.org/ns/two",
                 record_id="dataplant-tie", suppressed_by="ns"),
    ])
    assert vcr.report(data) == 0
    assert "uniqueId` tiebreak" in capsys.readouterr().out


def test_namespace_of_matches_the_dedup_rule():
    from harvester import dedup
    for url in (
        "https://git.nfdi4plants.org/ceplas/TGA_Basu26",
        "https://git.nfdi4plants.org/hhu_molphys_frommer/published/MGlucoMeter2_6",
        "https://git.nfdi4plants.org/lonely",
    ):
        assert vcr.namespace_of(url) == dedup.namespace_of(url)
