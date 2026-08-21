"""Enumeration diffing: whether tonight's harvest is warranted."""
from __future__ import annotations

from harvester import detect

_T0 = "2026-08-01T00:00:00Z"
_T1 = "2026-08-20T00:00:00Z"


def test_identical_enumerations_produce_an_empty_diff():
    d = detect.diff_enumeration({"ns/a": _T0}, {"ns/a": _T0})
    assert d.is_empty
    assert d == detect.EnumerationDiff(appeared=(), vanished=(), changed=())


def test_a_new_project_appears():
    d = detect.diff_enumeration({"ns/a": _T0, "ns/b": _T1}, {"ns/a": _T0})
    assert d.appeared == ("ns/b",)
    assert not d.is_empty


def test_a_removed_project_vanishes():
    d = detect.diff_enumeration({"ns/a": _T0}, {"ns/a": _T0, "ns/b": _T1})
    assert d.vanished == ("ns/b",)
    assert not d.is_empty


def test_a_pushed_project_changes():
    d = detect.diff_enumeration({"ns/a": _T1}, {"ns/a": _T0})
    assert d.changed == ("ns/a",)
    assert not d.is_empty


def test_results_are_sorted_so_logs_are_stable():
    d = detect.diff_enumeration({"ns/z": _T0, "ns/a": _T0}, {})
    assert d.appeared == ("ns/a", "ns/z")


def test_an_empty_published_snapshot_makes_everything_new():
    d = detect.diff_enumeration({"ns/a": _T0, "ns/b": _T0}, {})
    assert d.appeared == ("ns/a", "ns/b")
    assert d.vanished == () and d.changed == ()


def test_summary_names_the_counts():
    d = detect.diff_enumeration({"ns/a": _T1, "ns/b": _T0}, {"ns/a": _T0, "ns/c": _T0})
    assert d.summary() == "1 appeared, 1 vanished, 1 changed"
