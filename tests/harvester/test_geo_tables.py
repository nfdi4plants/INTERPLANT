"""Tests for the committed geodata lookup tables."""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import harvester.geo_tables as geo_tables_module
from harvester.geo_tables import _load, load_institutions, load_places, lookup


def test_institutions_table_loads() -> None:
    table = load_institutions()
    assert isinstance(table, dict)


def test_places_table_loads() -> None:
    table = load_places()
    assert isinstance(table, dict)


def test_lookup_returns_the_entry_for_a_known_key() -> None:
    table = {"Heinrich Heine University": {"point": [6.7926, 51.1889],
                                           "precision": "institution"}}
    assert lookup(table, "Heinrich Heine University")["precision"] == "institution"


def test_lookup_is_whitespace_and_case_insensitive() -> None:
    table = {"Heinrich Heine University": {"point": [6.7926, 51.1889],
                                           "precision": "institution"}}
    assert lookup(table, "  heinrich heine university  ") is not None


def test_lookup_returns_none_for_a_missing_key() -> None:
    assert lookup({}, "Nowhere Institute") is None


def test_an_explicit_null_entry_resolves_to_none() -> None:
    # A null records "looked up, nothing matched" and is distinct from a
    # missing key: it documents that a human has already seen this string.
    assert lookup({"AFFILIATION_PERSON2": None}, "AFFILIATION_PERSON2") is None


def test_lookup_prefers_an_exact_match_over_a_case_insensitive_scan_match() -> None:
    # If a table ever holds two case variants of the same string (the
    # refresher script dedupes case-insensitively to prevent this, but the
    # loader must not silently depend on that), the exact key match must win
    # regardless of dict insertion order or which of the two values is null.
    table = {
        "heinrich heine university": {"point": [6.7926, 51.1889], "precision": "institution"},
        "Heinrich Heine University": None,
    }
    assert lookup(table, "Heinrich Heine University") is None


def test_every_committed_entry_has_a_valid_shape() -> None:
    for name, table in (("institutions", load_institutions()), ("places", load_places())):
        assert table, f"{name} table must not be empty"
        for key, entry in table.items():
            if entry is None:
                continue
            assert "point" in entry, f"{name}[{key}] has no point"
            lon, lat = entry["point"]
            assert -180.0 <= lon <= 180.0, f"{name}[{key}] longitude out of range"
            assert -90.0 <= lat <= 90.0, f"{name}[{key}] latitude out of range"
            assert entry["precision"] in ("exact", "admin1", "country", "institution")


def test_seed_institutions_are_present_by_value() -> None:
    # A vacuous empty table must not pass: assert real seed content by value,
    # not just that load_institutions() returns "a dict".
    table = load_institutions()
    assert "AFFILIATION_PERSON2" in table
    assert table["AFFILIATION_PERSON2"] is None
    entry = lookup(table, "Heinrich Heine University")
    assert entry is not None
    assert entry["point"] == [6.7926, 51.1889]


def test_seed_places_are_present_by_value() -> None:
    table = load_places()
    entry = lookup(table, "Germany")
    assert entry is not None
    assert entry["precision"] == "country"
    assert entry["point"] == [10.4515, 51.1657]


def test_load_raises_for_a_missing_committed_file(tmp_path: Path) -> None:
    # Both institutions.json and places.json are committed; their absence is
    # a deployment bug, not a valid empty-table state, and must fail loud
    # rather than silently returning {}.
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        _load(missing)


def test_module_has_no_network_imports() -> None:
    # The single most important invariant of this module: resolution never
    # happens during a harvest, so geo_tables.py must not be able to reach
    # the network even by accident.
    source = inspect.getsource(geo_tables_module)
    for banned in ("import httpx", "import requests", "import urllib.request", "from httpx"):
        assert banned not in source, f"{banned!r} must not appear in harvester/geo_tables.py"
    for name in ("httpx", "requests", "urllib"):
        assert not hasattr(geo_tables_module, name), (
            f"{name} must not be bound in harvester.geo_tables's namespace"
        )
