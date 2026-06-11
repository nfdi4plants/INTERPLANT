"""Tests for harvester.extractors.organism."""
from __future__ import annotations

from harvester.extractors.organism import extract_organisms
from harvester.isa_reader import Investigation


def _inv(organisms: list[str]) -> Investigation:
    return Investigation(identifier="i", title="t", description=None, organisms=organisms)


def test_extract_organisms_dedups_and_sorts() -> None:
    inv = _inv(["Zea mays", "Arabidopsis thaliana", "Arabidopsis thaliana"])
    assert extract_organisms(inv) == ["Arabidopsis thaliana", "Zea mays"]


def test_extract_organisms_strips_and_drops_empty() -> None:
    inv = _inv(["  Arabidopsis thaliana ", "", "   "])
    assert extract_organisms(inv) == ["Arabidopsis thaliana"]


def test_extract_organisms_empty_returns_empty() -> None:
    assert extract_organisms(_inv([])) == []
