"""Unit tests for the acquisition layer."""
from __future__ import annotations

import subprocess
from pathlib import Path

from harvester import acquire

FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures" / "arcs"


def test_iter_local_arcs_finds_arc_dirs():
    ids = list(acquire.iter_local_arcs(FIXTURES_ROOT))
    names = {i.path for i in ids}
    assert "ArcPrototype" in names
    proto = next(i for i in ids if i.path == "ArcPrototype")
    assert proto.local_dir is not None
    assert proto.web_url.startswith("file://")


def test_clone_arc_retries_then_succeeds(monkeypatch, tmp_path):
    calls = {"n": 0}

    class FakeCompleted:
        def __init__(self, rc):
            self.returncode = rc
            self.stderr = "boom"
            self.stdout = ""

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        return FakeCompleted(1 if calls["n"] == 1 else 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    ok, err = acquire.clone_arc("https://g/one", tmp_path, retries=2)
    assert ok is True
    assert calls["n"] == 2


def test_clone_arc_returns_error_after_exhausting_retries(monkeypatch, tmp_path):
    class FakeCompleted:
        returncode = 1
        stderr = "fatal: not found"
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kwargs: FakeCompleted())
    ok, err = acquire.clone_arc("https://g/missing", tmp_path, retries=1)
    assert ok is False
    assert "not found" in err


def test_iter_live_arcs_skips_cost_excluded_paths(monkeypatch):
    """The mega-ARCs must be dropped before the clone, not after the parse."""
    metas = [
        {"path_with_namespace": "ceplas/Angermann-2024", "web_url": "https://g/a",
         "project_id": 1, "last_activity_at": "T1"},
        {"path_with_namespace": "usadellab/BreedingValue-Public-Dataset",
         "web_url": "https://g/b", "project_id": 2, "last_activity_at": "T2"},
    ]
    monkeypatch.setattr(acquire, "iter_public_arcs", lambda base, **kw: iter(metas))

    idents = list(acquire.iter_live_arcs("https://g"))

    assert [i.path for i in idents] == ["ceplas/Angermann-2024"]


def test_iter_local_arcs_does_not_apply_the_cost_exclusions(tmp_path, monkeypatch):
    """The manual escape hatch: `harvest --local-dir` and `ingest` must still
    handle a mega-ARC on demand. Local identities carry a bare directory name
    rather than a namespaced path, so the real predicate could never match one
    anyway; patching it to match the bare name is what gives this pin teeth, so
    it fails the moment anyone wires the check into iter_local_arcs."""
    monkeypatch.setattr(
        acquire, "is_cost_excluded", lambda p: p == "BreedingValue-Public-Dataset"
    )
    arc = tmp_path / "BreedingValue-Public-Dataset"
    arc.mkdir()
    (arc / "isa.investigation.xlsx").write_text("stub", encoding="utf-8")

    idents = list(acquire.iter_local_arcs(tmp_path))

    assert [i.path for i in idents] == ["BreedingValue-Public-Dataset"]
