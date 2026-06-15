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
        ("ChIP-Seq",           "genomics"),        # folded: epigenomics -> genomics
        ("ATAC-seq",           "genomics"),
        ("WGS",                "genomics"),
        ("phenotyping",        "phenotyping"),     # enum value, not 'phenomics'
        ("lipidomics",         "metabolomics"),    # folded: lipidomics -> metabolomics
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
        ("Lipidomics",                   "metabolomics"),
        ("protein expression profiling", "proteomics"),
        ("protein structure determination", "proteomics"),
        ("whole genome sequencing",      "genomics"),
        ("plant phenotyping",            "phenotyping"),
        ("Bacterial 16S RNA",            "microbiome"),
    ],
)
def test_classify_omics_by_measurement_type(mtype: str, expected: str) -> None:
    assert classify_omics("", measurement_type=mtype) == expected


def test_measurement_type_takes_precedence_over_folder() -> None:
    assert classify_omics("measurement1", measurement_type="metabolite profiling") == "metabolomics"


def test_classify_omics_falls_back_to_folder_when_no_measurement() -> None:
    assert classify_omics("RNA-Seq", measurement_type=None) == "transcriptomics"


def test_technology_type_classifies_when_folder_and_mtype_silent() -> None:
    assert classify_omics("data", technology_type="RNA-Seq") == "transcriptomics"


def test_microscope_platform_classifies_imaging() -> None:
    assert classify_omics("data", technology_platform="Zeiss LSM 880 confocal") == "imaging"


def test_ambiguous_sequencer_platform_does_not_classify() -> None:
    # A sequencer model alone cannot disambiguate genomics vs transcriptomics.
    assert classify_omics("data", technology_platform="Illumina NovaSeq 6000") is None


def test_ambiguous_mass_spec_platform_does_not_classify() -> None:
    assert classify_omics("data", technology_platform="Thermo Q Exactive") is None
