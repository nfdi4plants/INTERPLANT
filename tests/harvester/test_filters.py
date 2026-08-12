"""Exclusion rules that keep template ARCs out of the catalog."""
from __future__ import annotations

from dataclasses import dataclass, field

from harvester import filters


@dataclass
class FakeAssay:
    folder: str


@dataclass
class FakeStudy:
    assays: list = field(default_factory=list)


@dataclass
class FakeInvestigation:
    identifier: str
    studies: list = field(default_factory=list)


def _inv(identifier: str, *folders: str) -> FakeInvestigation:
    return FakeInvestigation(
        identifier=identifier,
        studies=[FakeStudy(assays=[FakeAssay(folder=f) for f in folders])],
    )


def test_all_template_assays_are_excluded():
    verdict = filters.evaluate(_inv("SomeRealName", "measurement1", "Assay2"))
    assert verdict.excluded is True
    assert verdict.rule == "template-assays"


def test_one_real_assay_keeps_the_arc():
    """The 'no non-template assay' conjunct - a real assay rescues the ARC."""
    verdict = filters.evaluate(_inv("SomeRealName", "measurement1", "proteinAssay"))
    assert verdict.excluded is False
    assert verdict.rule == ""


def test_arc_with_no_assays_is_not_excluded_by_the_template_rule():
    """Empty ARCs are spec rule 3.1, deliberately out of scope here."""
    assert filters.evaluate(_inv("SomeRealName")).excluded is False


def test_placeholder_identifier_is_excluded_even_with_real_assays():
    verdict = filters.evaluate(_inv("yourInvestigationName", "proteinAssay"))
    assert verdict.excluded is True
    assert verdict.rule == "placeholder-identifier"


def test_placeholder_prefixes_match_on_a_boundary():
    assert filters.evaluate(_inv("MinExample_Proteomics", "proteinAssay")).excluded is True
    assert filters.evaluate(_inv("SampleARC_Proteomics", "proteinAssay")).excluded is True
    # A real ARC that merely starts with the same letters must survive.
    assert filters.evaluate(_inv("SampleArcadiaSurvey", "proteinAssay")).excluded is False


def test_every_exclusion_confirmed_on_the_live_corpus_stays_excluded():
    """The four investigations the 2026-08-12 full-corpus run excluded.

    Report: harvest-runs/harvest-20260812T105010Z.json. All 8 excluded ARCs
    reduce to these four investigations, and every copy of each is dropped, so
    none of them reaches the database. The user confirmed all four are genuinely
    templates, which is the evidence the module docstring requires before the
    placeholder list is trusted.

    Pinned because loosening either rule would silently re-admit templates into
    the catalog AWI ingests - and a template that reappears looks like real data.
    """
    # yourInvestigationName: 3 ARCs (arc_templates/arc, DiP/DiP-KS/dip-ressourcen,
    # marcel/test-template). Caught by template-assays in the live repos, and by
    # the placeholder rule on the identifier alone.
    assert filters.evaluate(_inv("yourInvestigationName", "proteinAssay")).excluded is True

    # MinExample_Proteomics: 2 ARCs (hsaker/NewArc, martinkuhl/SampleARC_Proteomics).
    assert filters.evaluate(_inv("MinExample_Proteomics", "proteinAssay")).excluded is True

    # samplearc_nfcore: 1 ARC (perelo/samplearc_nfcore), no twin - excluded by
    # the boundary-matched `samplearc` prefix, not by its assay folders.
    assert filters.evaluate(_inv("samplearc_nfcore", "proteinAssay")).excluded is True

    # ArcPrototype: 2 ARCs (kMutagene, muehlhaus). The identifier is NOT a
    # placeholder - only the assay folders give it away, which is why the live
    # repos trip template-assays while tests/fixtures/arcs/ArcPrototype (folder
    # "RNA-Seq") is deliberately kept as a valid ARC for pipeline tests.
    assert filters.evaluate(_inv("ArcPrototype", "assay1", "measurement2")).excluded is True
    assert filters.evaluate(_inv("ArcPrototype", "RNA-Seq")).excluded is False


def test_template_assay_rule_is_case_insensitive():
    assert filters.evaluate(_inv("Real", "ASSAY1", "YourAssayName")).excluded is True
