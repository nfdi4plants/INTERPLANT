"""Tests for harvester.ids.mint_id."""
from __future__ import annotations

import pytest

from harvester import ids
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


def test_normalize_is_public_and_collapses_punctuation():
    assert ids.normalize("MinExample_Proteomics") == "minexample-proteomics"
    assert ids.normalize("  Spaced   Title!! ") == "spaced-title"


def test_disambiguate_id_appends_six_hex_of_unique_id():
    new_id = ids.disambiguate_id(
        "dataplant-potatoassemblyarc",
        "3f2a1b9c-0d4e-5f6a-8b7c-9d0e1f2a3b4c",
    )
    assert new_id == "dataplant-potatoassemblyarc-3f2a1b"


def test_disambiguated_id_matches_the_record_schema_pattern():
    import re

    new_id = ids.disambiguate_id(
        "dataplant-quinoa-chileanfieldtrial",
        "abcdef01-2345-6789-abcd-ef0123456789",
    )
    assert re.fullmatch(r"^[a-z0-9][a-z0-9-]*$", new_id)


def test_disambiguate_id_lowercases_an_uppercase_unique_id():
    import re

    new_id = ids.disambiguate_id(
        "dataplant-quinoa-chileanfieldtrial",
        "ABCDEF01-2345-6789-ABCD-EF0123456789",
    )
    assert new_id == "dataplant-quinoa-chileanfieldtrial-abcdef"
    assert re.fullmatch(r"^[a-z0-9][a-z0-9-]*$", new_id)
