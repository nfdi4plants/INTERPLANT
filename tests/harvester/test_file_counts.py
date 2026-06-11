"""Tests for harvester.extractors.file_counts."""
from __future__ import annotations

from pathlib import Path

from harvester.extractors.file_counts import count_assay_files


def test_count_assay_files_raw_and_derived(tmp_path: Path) -> None:
    base = tmp_path / "assays" / "rna"
    (base / "dataset").mkdir(parents=True)
    (base / "dataset" / "r1.fastq").write_text("x", encoding="utf-8")
    (base / "dataset" / "r2.fastq").write_text("x", encoding="utf-8")
    (base / "isa.assay.xlsx").write_text("x", encoding="utf-8")
    (base / "processed").mkdir()
    (base / "processed" / "counts.tsv").write_text("x", encoding="utf-8")

    assert count_assay_files(tmp_path, "rna") == {"raw": 2, "derived": 1}


def test_count_assay_files_missing_folder(tmp_path: Path) -> None:
    assert count_assay_files(tmp_path, "nope") == {"raw": 0, "derived": 0}
