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
