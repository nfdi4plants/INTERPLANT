"""Count raw vs derived files for an assay folder on disk.

Heuristic (documented, not a hard ISA distinction):
  raw     = files under assays/<folder>/dataset/
  derived = other files under assays/<folder>/, excluding dataset/ and the
            isa.assay.xlsx metadata file.

Author: Mohamed Abouzid m.abouzid@fz-juelich.de
"""
from __future__ import annotations

from pathlib import Path


def count_assay_files(arc_root: Path, assay_folder: str) -> dict[str, int]:
    base = arc_root / "assays" / assay_folder
    if not base.is_dir():
        return {"raw": 0, "derived": 0}
    raw = sum(1 for p in (base / "dataset").rglob("*") if p.is_file())
    derived = 0
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(base)
        if rel.parts and rel.parts[0] == "dataset":
            continue
        if p.name == "isa.assay.xlsx":
            continue
        derived += 1
    return {"raw": raw, "derived": derived}
