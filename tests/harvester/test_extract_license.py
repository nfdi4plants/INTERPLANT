"""Tests for harvester.extractors.license."""
from __future__ import annotations

from pathlib import Path

from harvester.extractors.license import extract_license
from harvester.isa_reader import Investigation


def _inv(license_value: str | None) -> Investigation:
    return Investigation(identifier="i", title="t", description=None, license=license_value)


def test_extract_license_prefers_investigation_comment(tmp_path: Path) -> None:
    assert extract_license(_inv("CC-BY-4.0"), tmp_path) == "CC-BY-4.0"


def test_extract_license_falls_back_to_license_file_first_line(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text("MIT License\n\nCopyright ...", encoding="utf-8")
    assert extract_license(_inv(None), tmp_path) == "MIT License"


def test_extract_license_returns_none_when_absent(tmp_path: Path) -> None:
    assert extract_license(_inv(None), tmp_path) is None
