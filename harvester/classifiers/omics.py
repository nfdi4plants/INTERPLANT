"""Omics-domain classifier.

Classifies an assay into an omics_domain vocab key. Prefers the ISA assay
measurement type (richer, ~73% populated on real ARCs); falls back to the
assay folder name. Vocab lives in omics_vocab.yaml so it is hand-editable.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

_VOCAB_PATH = Path(__file__).parent / "omics_vocab.yaml"


@lru_cache(maxsize=1)
def _vocab() -> dict:
    return yaml.safe_load(_VOCAB_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _folder_rules() -> list[tuple[re.Pattern[str], str]]:
    return [(re.compile(r["pattern"]), r["domain"]) for r in _vocab()["rules"]]


@lru_cache(maxsize=1)
def _measurement_rules() -> list[tuple[re.Pattern[str], str]]:
    raw = _vocab().get("measurement_type_rules", [])
    return [(re.compile(r["pattern"]), r["domain"]) for r in raw]


def classify_omics(folder_name: str, measurement_type: str | None = None) -> str | None:
    """Return the omics_domain vocab key, or None when no rule matches."""
    if measurement_type:
        for pattern, domain in _measurement_rules():
            if pattern.search(measurement_type):
                return domain
    if folder_name:
        for pattern, domain in _folder_rules():
            if pattern.search(folder_name):
                return domain
    return None
