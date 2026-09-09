"""Tests for ISA header classification in harvester.extractors.location."""
from __future__ import annotations

import pytest

from harvester.extractors.location import (
    axis_of,
    is_place_header,
    role_from_header,
    unwrap_header,
)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Parameter [longitude]", "longitude"),
        # singular Characteristic: used by MARS_ENA-Metabolights and DAP_Seq
        ("Characteristic [latitude]", "latitude"),
        ("Characteristics [latitude]", "latitude"),
        ("Factor [lat]", "lat"),
        ("Comment[Latitude]", "Latitude"),
        ("Parameter [Biological material latitude]", "Biological material latitude"),
        # unwrapped headers pass through
        ("collection latitude", "collection latitude"),
        ("Longitude", "Longitude"),
    ],
)
def test_unwrap_header_strips_the_isa_wrapper(header, expected) -> None:
    assert unwrap_header(header) == expected


@pytest.mark.parametrize(
    ("core", "expected"),
    [
        ("latitude", "lat"),
        ("Latitude", "lat"),
        ("longitude", "lon"),
        ("Longitude", "lon"),
        ("Biological material latitude", "lat"),
        ("Material source longitude", "lon"),
        ("collection latitude", "lat"),
        ("Geographic location (latitude)", "lat"),
        ("Geographic location (longitude)", "lon"),
        # not an axis
        ("Biological material coordinates uncertainty", None),
        ("Altitude", None),
        ("organism", None),
    ],
)
def test_axis_of_identifies_the_coordinate_axis(core, expected) -> None:
    assert axis_of(core) == expected


@pytest.mark.parametrize(
    ("core", "expected"),
    [
        ("Geographic location (latitude)", "experiment-site"),
        ("Biological material latitude", "material-origin"),
        ("Material source longitude", "material-source"),
        ("collection latitude", "collection-site"),
        # ad-hoc headers declare nothing; the caller falls back to geo_roles
        ("latitude", None),
        ("Longitude", None),
    ],
)
def test_role_from_header_only_when_the_header_declares_one(core, expected) -> None:
    assert role_from_header(core) == expected


@pytest.mark.parametrize(
    "core",
    [
        "Location",
        "geographic location",
        "Geographic location (country)",
        "geographic area",
        "Country Code",
        "Origin Country",
        "country_or_area",
        "ESTADO",
        "PAIS",
    ],
)
def test_is_place_header_accepts_measured_place_columns(core) -> None:
    assert is_place_header(core) is True


@pytest.mark.parametrize(
    "core",
    [
        # REGRESSION: the German "ort" matches inside all of these
        "detector type",
        "reporter",
        "vortexing",
        "Vortex Mixer",
        "master resort",
        "Suppressor type",
        # REGRESSION: "row" matches inside "growth"
        "growth day length",
        "Growth Medium",
        "plant growth medium exposure",
        # REGRESSION: "location" and "site" in non-geographic senses
        "Memory allocation",
        "Dataset FTP location",
        "Data Location",
        "Cloning Site",
        "restriction sites",
        "Restriction digestion site",
        "insertion Site",
        "Infiltration site",
        "Coding Region",
        # REGRESSION: "state" is a sample state, not a place
        "sample state",
        "biosource material state",
        "bioreactor type",
        "sensor type",
    ],
)
def test_is_place_header_rejects_the_measured_false_positives(core) -> None:
    assert is_place_header(core) is False
