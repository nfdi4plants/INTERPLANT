"""Tests for harvester.classifiers.omics."""
from __future__ import annotations

import pytest

from harvester.classifiers.omics import classify_omics


@pytest.mark.parametrize(
    "folder,expected",
    [
        ("RNA-Seq",            "transcriptomics"),
        ("rna_seq",            "transcriptomics"),
        ("rnaseq",             "transcriptomics"),
        ("LC-MS_metabolites",  "metabolomics"),
        ("LC-MS-proteins",     "proteomics"),
        ("MALDI-imaging",      "metabolomics"),
        ("ChIP-Seq",           "epigenomics"),
        ("WGS",                "genomics"),
        ("phenotyping",        "phenomics"),
    ],
)
def test_classify_omics_known_folders(folder: str, expected: str) -> None:
    assert classify_omics(folder) == expected


@pytest.mark.parametrize("folder", ["measurement1", "unknown-assay", "", "weather-station"])
def test_classify_omics_unknown_returns_none(folder: str) -> None:
    assert classify_omics(folder) is None


@pytest.mark.parametrize(
    "mtype,expected",
    [
        ("transcription profiling",      "transcriptomics"),
        ("metabolite profiling",         "metabolomics"),
        ("protein expression profiling", "proteomics"),
        ("whole genome sequencing",      "genomics"),
        ("plant phenotyping",            "phenomics"),
    ],
)
def test_classify_omics_by_measurement_type(mtype: str, expected: str) -> None:
    assert classify_omics("", measurement_type=mtype) == expected


def test_measurement_type_takes_precedence_over_folder() -> None:
    assert classify_omics("measurement1", measurement_type="metabolite profiling") == "metabolomics"


def test_classify_omics_falls_back_to_folder_when_no_measurement() -> None:
    assert classify_omics("RNA-Seq", measurement_type=None) == "transcriptomics"
