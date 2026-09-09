"""Tests for coordinate value parsing in harvester.extractors.location."""
from __future__ import annotations

import pytest

from harvester.extractors.location import parse_coord


@pytest.mark.parametrize(
    ("raw", "axis", "expected"),
    [
        # plain decimal, float or text (most of the corpus)
        (18.48583333, "lat", 18.485833),
        ("18.48583333", "lat", 18.485833),
        (-99.79166667, "lon", -99.791667),
        # explicit leading plus, stored as text (agdafair/flyover_redacted)
        ("+49.42608333", "lat", 49.426083),
        ("+6.21", "lon", 6.21),
        # comma decimal separator with hemisphere suffix (Cassava)
        ("12,73322°N", "lat", 12.73322),
        ("101,13511°E", "lon", 101.13511),
        # degree symbol with spaced hemisphere suffix (Methodfungalhyphae)
        ("50.925617° N", "lat", 50.925617),
        ("6.936641° E", "lon", 6.936641),
        # degrees-minutes with hemisphere suffix (quinoa)
        ("28°34′ S", "lat", -28.566667),
        ("70°47′ W", "lon", -70.783333),
        # southern and western hemispheres negate
        ("12.5 S", "lat", -12.5),
        ("30.25 W", "lon", -30.25),
    ],
)
def test_parse_coord_accepts_every_observed_format(raw, axis, expected) -> None:
    assert parse_coord(raw, axis=axis) == pytest.approx(expected, abs=1e-6)


def test_hemisphere_suffix_overrides_a_leading_sign() -> None:
    # W means negative regardless of the written sign.
    assert parse_coord("+70.5 W", axis="lon") == pytest.approx(-70.5)


@pytest.mark.parametrize(
    ("raw", "axis"),
    [
        # zarah.sorger/GH25_Sorger_2025 has a misaligned table: cells hold a file path
        ("./studies/Organisms/protocols/ArabidopsisGrowth.md", "lat"),
        # arc_templates/Genomics_ARC is an empty template
        (None, "lat"),
        ("", "lat"),
        ("   ", "lon"),
        # out of range
        ("91.0", "lat"),
        ("-90.5", "lat"),
        ("181.0", "lon"),
        ("-180.5", "lon"),
        # a coordinates-uncertainty column holds metres, not degrees
        ("222000", "lon"),
        ("not a number", "lon"),
    ],
)
def test_parse_coord_rejects_unusable_values(raw, axis) -> None:
    assert parse_coord(raw, axis=axis) is None
