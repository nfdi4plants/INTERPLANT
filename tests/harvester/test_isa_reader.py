"""Tests for harvester.isa_reader against the ArcPrototype fixture."""
from __future__ import annotations

from pathlib import Path

import pytest

from harvester.isa_reader import IsaReader

FIXTURE = Path(__file__).parent.parent / "fixtures" / "arcs" / "ArcPrototype"


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
