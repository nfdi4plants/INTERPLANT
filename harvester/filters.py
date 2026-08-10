"""Policy exclusions applied after parse and before build.

Spec: docs/specs/harvester.md section 4. Only the Template rule (4.2) and the
Placeholder-identifier rule (4.4) are implemented here; Empty (4.1) and
QC-only (4.3) are deliberately deferred.

Exclusion is NOT a parse failure. "Excluded by policy" and "broken data" are
different facts about an ARC, and collapsing them would make the audit report
misstate corpus health.

Both rules are literal, never fuzzy. A heuristic here would silently drop real
research data, so the placeholder list grows only by evidence from a run report.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from harvester.ids import normalize

_TEMPLATE_ASSAY = re.compile(r"^(yourassayname|assay[0-9]*|measurement[0-9]*)$")

# Normalized investigation identifiers shipped by ARC templates.
_PLACEHOLDER_EXACT = frozenset({"yourinvestigationname"})
_PLACEHOLDER_PREFIXES = ("minexample", "samplearc")


@dataclass(frozen=True)
class FilterVerdict:
    """Why an ARC was excluded, or that it was kept."""

    excluded: bool
    rule: str = ""


_KEEP = FilterVerdict(excluded=False)


def _assay_folders(investigation) -> list[str]:
    return [
        assay.folder
        for study in investigation.studies
        for assay in study.assays
    ]


def _is_template_assay(folder: str) -> bool:
    return bool(_TEMPLATE_ASSAY.fullmatch(normalize(folder)))


def _is_placeholder_identifier(identifier: str) -> bool:
    value = normalize(identifier or "")
    if value in _PLACEHOLDER_EXACT:
        return True
    # Boundary match only: "samplearc-proteomics" hits, "samplearcadiasurvey" does not.
    return any(value == p or value.startswith(f"{p}-") for p in _PLACEHOLDER_PREFIXES)


def evaluate(investigation) -> FilterVerdict:
    """Return the first exclusion rule that fires, or a keep verdict."""
    folders = _assay_folders(investigation)
    if folders and all(_is_template_assay(f) for f in folders):
        return FilterVerdict(excluded=True, rule="template-assays")

    if _is_placeholder_identifier(investigation.identifier):
        return FilterVerdict(excluded=True, rule="placeholder-identifier")

    return _KEEP
