"""Tests for the curated ARC-path to location-role map."""
from __future__ import annotations

import pytest

from harvester.geo_roles import GEO_ROLE_OVERRIDES, role_for_arc


@pytest.mark.parametrize(
    ("arc_path", "expected"),
    [
        ("usadellab/Teosinte", "collection-site"),
        ("tntranloc/dormancy_NhuTran_2025", "collection-site"),
        ("usadellab/Cassava_genome_sequencing_2017", "collection-site"),
        ("agdafair/flyover_redacted", "experiment-site"),
        ("imetzen1/Methodfungalhyphae", "experiment-site"),
        ("frommer/DAP_Seq", "experiment-site"),
        ("x.zhou/MARS_ENA-Metabolights", "experiment-site"),
    ],
)
def test_curated_roles_are_returned(arc_path, expected) -> None:
    assert role_for_arc(arc_path) == expected


def test_unlisted_arc_has_no_curated_role() -> None:
    assert role_for_arc("some/never-reviewed-arc") is None


def test_matching_is_exact_never_fuzzy() -> None:
    # A prefix or a case variant must NOT match: a heuristic here would
    # silently attach a wrong role to real research data.
    assert role_for_arc("usadellab/Teosinte-fork") is None
    assert role_for_arc("usadellab/teosinte") is None
    assert role_for_arc("Teosinte") is None


def test_curated_roles_use_only_the_two_permitted_values() -> None:
    # material-origin and material-source are assigned ONLY from their literal
    # MIAPPE headers, never by curation, so a curated role can never imply a
    # MIAPPE field the ARC does not contain.
    assert set(GEO_ROLE_OVERRIDES.values()) <= {"experiment-site", "collection-site"}
