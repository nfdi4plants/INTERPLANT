"""Extract the distinct organism list from a parsed Investigation.

Author: Mohamed Abouzid m.abouzid@fz-juelich.de
"""
from __future__ import annotations

from harvester.isa_reader import Investigation


def extract_organisms(investigation: Investigation) -> list[str]:
    """Return sorted, de-duplicated, non-empty organism names."""
    seen = {o.strip() for o in investigation.organisms if o and o.strip()}
    return sorted(seen)
