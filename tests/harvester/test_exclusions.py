"""Unit tests for the cost-based enumeration exclusions."""
from __future__ import annotations

from harvester import exclusions


def test_each_documented_mega_arc_is_excluded():
    for path in (
        "usadellab/BreedingValue-Public-Dataset",
        "lange/Curated_wheat_historical_phenotypic_data_from_European_Genebanks",
        "arendd/Historical_Phenomics_Wheat_Collection_IPK",
        "torsten.stoeter/rat-mri-ls",
    ):
        assert exclusions.is_cost_excluded(path), path


def test_an_ordinary_arc_is_not_excluded():
    assert not exclusions.is_cost_excluded("ceplas/Angermann-2024")


def test_matching_is_exact_not_prefix_or_suffix():
    """A heuristic here would silently drop real research data, so a path that
    merely contains or extends an excluded one must still be harvested."""
    assert not exclusions.is_cost_excluded("usadellab/BreedingValue-Public-Dataset-2")
    assert not exclusions.is_cost_excluded("BreedingValue-Public-Dataset")
    assert not exclusions.is_cost_excluded("other/BreedingValue-Public-Dataset")


def test_the_set_holds_exactly_the_four_documented_arcs():
    """Pins the list against silent growth: a fifth entry is a decision that
    needs its own measurement, not a drive-by edit."""
    assert len(exclusions.COST_EXCLUDED_PATHS) == 4
