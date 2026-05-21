"""Omics-domain classifier.

Input: an ARC assay folder name (e.g. "RNA-Seq", "measurement1").
Output: an `omics_domain` value matching the controlled vocabulary in
docs/specs/schemas/record.schema.json, or None if no rule matches.

The vocabulary lives in omics_vocab.yaml next to this module so it can be
hand-edited without touching code.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

_VOCAB_PATH = Path(__file__).parent / "omics_vocab.yaml"


@lru_cache(maxsize=1)
def _rules() -> list[tuple[re.Pattern[str], str]]:
    raw = yaml.safe_load(_VOCAB_PATH.read_text(encoding="utf-8"))
    return [(re.compile(rule["pattern"]), rule["domain"]) for rule in raw["rules"]]


def classify_omics(folder_name: str) -> str | None:
    """Return the omics_domain for `folder_name`, or None when no rule matches."""
    if not folder_name:
        return None
    for pattern, domain in _rules():
        if pattern.search(folder_name):
            return domain
    return None
