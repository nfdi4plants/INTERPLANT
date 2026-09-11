"""Tests for ISA header classification in harvester.extractors.location."""
from __future__ import annotations

import pytest

from harvester.extractors.location import (
    axis_of,
    is_place_header,
    is_structural_header,
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
    ("header", "expected"),
    [
        ("Term Source REF", True),
        ("Term Accession Number", True),
        ("Unit", True),
        ("Parameter [longitude]", False),
    ],
)
def test_is_structural_header_pins_the_three_isa_wrapper_columns(header, expected) -> None:
    assert is_structural_header(header) is expected


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
        # Every place header measured in the 14 place-name ARCs
        # (docs/progress/2026-09-09-location-coverage-report.md:176-191). The
        # word-list tightening in Finding A (dropping "area"/"origin"/"state")
        # must not silently drop any of these back to False.
        "Location",
        "Geographic location (country)",
        "geographic location",
        "Country Code",
        "geographic area",
        "Origin Country",
        "country_or_area",
    ],
)
def test_is_place_header_still_accepts_every_measured_true_positive(core) -> None:
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
        # Token-subset cases: a suffixed or annotated variant of a denied
        # base must be denied too, not just the exact base string.
        "Cloning site 2",
        "TATA box site",
        "restriction sites 3",
        # Finding A variants: "area", "origin" and "state" carry real
        # plant/omics false positives, which is why they were dropped from
        # _PLACE_WORDS rather than added to the deny list.
        "sample state (fresh/frozen)",
        "plant material state",
        "developmental state",
        "Data location URL",
        "Coding region 1",
        "leaf area",
        "surface area",
        "area under curve",
        "replication origin",
        "Vector origin",
    ],
)
def test_is_place_header_rejects_the_measured_false_positives(core) -> None:
    assert is_place_header(core) is False
