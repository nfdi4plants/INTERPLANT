"""Tests for harvester.isa_reader against the ArcPrototype fixture."""
from __future__ import annotations

from pathlib import Path

import pytest

from harvester.isa_reader import Assay, IsaReader, _assemble_studies

FIXTURE = Path(__file__).parent.parent / "fixtures" / "arcs" / "ArcPrototype"


def _assay(folder: str) -> Assay:
    return Assay(name=folder, folder=folder, measurement_type=None)


# ---------------------------------------------------------------------------
# Study/assay assembly logic.
#
# Real public ARCs frequently leave the "Registered Assay Identifiers" column
# empty in isa.investigation.xlsx even though assays/<name>/isa.assay.xlsx files
# exist on disk and surface in arc.Assays (see
# docs/progress/2026-06-10-linkage-investigation.md: 5/5 zero-assay ARCs were
# this bug, not real sparsity).  The assembler must not drop those assays.
# ---------------------------------------------------------------------------
def test_assemble_attaches_only_registered_assays_when_registration_present() -> None:
    assays = [_assay("a1"), _assay("a2"), _assay("a3")]
    specs = [("s1", "Study 1", ["a1", "a2"])]

    studies = _assemble_studies(specs, assays)

    assert len(studies) == 1
    assert {a.folder for a in studies[0].assays} == {"a1", "a2"}


def test_assemble_attaches_all_assays_when_registration_empty() -> None:
    assays = [_assay("a1"), _assay("a2")]
    specs = [("s1", "Study 1", [])]

    studies = _assemble_studies(specs, assays)

    assert {a.folder for a in studies[0].assays} == {"a1", "a2"}


def test_assemble_synthesizes_study_when_no_studies_but_assays_exist() -> None:
    assays = [_assay("a1")]

    studies = _assemble_studies([], assays)

    assert len(studies) == 1
    assert {a.folder for a in studies[0].assays} == {"a1"}


def test_assemble_returns_empty_when_no_studies_and_no_assays() -> None:
    assert _assemble_studies([], []) == []


@pytest.fixture(scope="module")
def investigation():
    return IsaReader().read(FIXTURE)


def test_reader_returns_non_empty_title(investigation) -> None:
    assert investigation.title
    assert isinstance(investigation.title, str)


def test_reader_returns_identifier(investigation) -> None:
    assert investigation.identifier


def test_reader_returns_two_studies(investigation) -> None:
    assert len(investigation.studies) == 2


def test_reader_returns_assays_per_study(investigation) -> None:
    all_assays = [a for s in investigation.studies for a in s.assays]
    assay_folders = {a.folder for a in all_assays}
    assert {"measurement1", "measurement2"} <= assay_folders


def test_reader_assays_have_folder_names(investigation) -> None:
    for study in investigation.studies:
        for assay in study.assays:
            assert assay.folder
            assert isinstance(assay.folder, str)
