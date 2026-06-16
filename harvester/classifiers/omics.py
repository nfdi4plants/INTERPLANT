"""Omics-domain classifier.

Classifies an assay into an omics_domain vocab key, emitting schema-enum values
directly. Signal precedence (first match wins): measurement_type, then
technology_type, then technology_platform, then the assay folder name. Vocab
lives in omics_vocab.yaml so it is hand-editable.
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


@lru_cache(maxsize=1)
def _technology_type_rules() -> list[tuple[re.Pattern[str], str]]:
    raw = _vocab().get("technology_type_rules", [])
    return [(re.compile(r["pattern"]), r["domain"]) for r in raw]


@lru_cache(maxsize=1)
def _technology_platform_rules() -> list[tuple[re.Pattern[str], str]]:
    raw = _vocab().get("technology_platform_rules", [])
    return [(re.compile(r["pattern"]), r["domain"]) for r in raw]


def classify_omics(
    folder_name: str,
    measurement_type: str | None = None,
    technology_type: str | None = None,
    technology_platform: str | None = None,
) -> str | None:
    """Return the omics_domain vocab key, or None when no rule matches.

    Signal precedence (first match wins): measurement_type, technology_type,
    technology_platform, folder name.
    """
    if measurement_type:
        for pattern, domain in _measurement_rules():
            if pattern.search(measurement_type):
                return domain
    if technology_type:
        for pattern, domain in _technology_type_rules():
            if pattern.search(technology_type):
                return domain
    if technology_platform:
        for pattern, domain in _technology_platform_rules():
            if pattern.search(technology_platform):
                return domain
    if folder_name:
        for pattern, domain in _folder_rules():
            if pattern.search(folder_name):
                return domain
    return None
