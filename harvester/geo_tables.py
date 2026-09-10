"""Load the committed geodata lookup tables.

Resolution never happens during a harvest. harvester/publish.py keeps its gate
"deliberately pure - no database, no clock", and the AWI portal harvests a full
dump with a 5-day TTL, so one ROR timeout would strip geometry from ~151
records and show them unmapped until the next good run. Committed tables also
make every match reviewable in a git diff, which is how a wrong match or a
template placeholder such as AFFILIATION_PERSON2 gets caught.

Refresh with `uv run python scripts/resolve_geodata.py`, the same
on-demand pattern scripts/pin_portal_schema.py uses for the portal schema.

Named geo_tables (not geodata) so this module cannot collide with the
harvester/geodata/ data directory.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

GEODATA_DIR = Path(__file__).parent / "geodata"
INSTITUTIONS_PATH = GEODATA_DIR / "institutions.json"
PLACES_PATH = GEODATA_DIR / "places.json"


def _load(path: Path) -> dict[str, dict | None]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_institutions() -> dict[str, dict | None]:
    """Affiliation string to resolved institution, or None when unresolvable."""
    return _load(INSTITUTIONS_PATH)


@lru_cache(maxsize=1)
def load_places() -> dict[str, dict | None]:
    """Place name to resolved gazetteer entry, or None when unresolvable."""
    return _load(PLACES_PATH)


def lookup(table: dict[str, dict | None], key: str) -> dict | None:
    """Case- and whitespace-insensitive lookup. None when absent or explicitly null."""
    if not key:
        return None
    entry = table.get(key)
    if entry is not None:
        return entry
    wanted = key.strip().casefold()
    for candidate, value in table.items():
        if candidate.strip().casefold() == wanted:
            return value
    return None
