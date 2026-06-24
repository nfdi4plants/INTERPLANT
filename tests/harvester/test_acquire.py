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
