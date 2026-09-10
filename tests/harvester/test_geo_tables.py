"""Tests for the committed geodata lookup tables."""
from __future__ import annotations

from harvester.geo_tables import load_institutions, load_places, lookup


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


def test_every_committed_entry_has_a_valid_shape() -> None:
    for name, table in (("institutions", load_institutions()), ("places", load_places())):
        for key, entry in table.items():
            if entry is None:
                continue
            assert "point" in entry, f"{name}[{key}] has no point"
            lon, lat = entry["point"]
            assert -180.0 <= lon <= 180.0, f"{name}[{key}] longitude out of range"
            assert -90.0 <= lat <= 90.0, f"{name}[{key}] latitude out of range"
            assert entry["precision"] in ("exact", "admin1", "country", "institution")
