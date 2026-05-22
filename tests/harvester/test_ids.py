"""Tests for harvester.ids.mint_id."""
from __future__ import annotations

import pytest

from harvester.ids import mint_id


@pytest.mark.parametrize(
    "provider,slug,expected",
    [
        ("dataplant", "ArcPrototype", "dataplant-arcprototype"),
        ("dataplant", "arc-prototype", "dataplant-arc-prototype"),
        ("dataplant", "My ARC With Spaces", "dataplant-my-arc-with-spaces"),
        ("dataplant", "Weird__Under_scores", "dataplant-weird-under-scores"),
        ("dataplant", "MiXeD-CASE_Slug", "dataplant-mixed-case-slug"),
    ],
)
def test_mint_id_normalizes_slug(provider: str, slug: str, expected: str) -> None:
    assert mint_id(provider, slug) == expected


def test_mint_id_empty_provider_rejected() -> None:
    with pytest.raises(ValueError):
        mint_id("", "ArcPrototype")


def test_mint_id_empty_slug_rejected() -> None:
    with pytest.raises(ValueError):
        mint_id("dataplant", "")
