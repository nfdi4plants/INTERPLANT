"""Resolve ARC affiliation strings and place names to coordinates.

Run this ON DEMAND only, never as part of a harvest:

    uv run python scripts/resolve_geodata.py --affiliations affils.txt
    uv run python scripts/resolve_geodata.py --places places.txt

Add --dry-run to see which strings are new (not already a key in the
committed table, case- and whitespace-insensitively) without making any
network call or touching the file.

It rewrites harvester/geodata/institutions.json and places.json sorted by key,
so a review of the diff can catch a wrong match. Unresolved or low-confidence
strings are written as an explicit null, which records "looked up, nothing
matched" and is distinct from a key that was never tried. Keys already
present in the committed table - matched case- and whitespace-insensitively,
the same rule harvester.geo_tables.lookup uses - are left untouched, so a
re-run never silently overwrites a reviewed entry and never adds a case
variant of a key that already has a reviewed answer. Delete the existing key
first if it needs re-resolving. The file is left untouched (no write at all)
when a run resolves nothing new.

Same pattern as scripts/pin_portal_schema.py: the committed copy is what the
harvester reads, and refreshing it is a deliberate, reviewable act.

Author: Mohamed Abouzid m.abouzid@fz-juelich.de
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTITUTIONS = REPO_ROOT / "harvester" / "geodata" / "institutions.json"
PLACES = REPO_ROOT / "harvester" / "geodata" / "places.json"

ROR_API = "https://api.ror.org/organizations"
NOMINATIM_API = "https://nominatim.openstreetmap.org/search"

# Below this ROR match score an entry is written as null for human review
# rather than accepted. Chosen against the 412 real affiliation strings; raise
# it if the diff shows wrong matches, lower it if too much lands in null.
# TODO: this threshold has not been tuned against a live run yet.
MIN_CONFIDENCE = 0.8

# Nominatim's usage policy caps unauthenticated requests at 1/second; a bulk
# --places run without this would be throttled or blocked. ROR has no such
# documented cap, so no delay is applied to affiliation resolution.
NOMINATIM_DELAY_SECONDS = 1.0

_UA = {"User-Agent": "interplant-geodata-resolver (m.abouzid@fz-juelich.de)"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save(path: Path, table: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(table, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {path} ({len(table)} entries)")


def resolve_affiliation(client: httpx.Client, raw: str) -> dict | None:
    """Match one affiliation string to a ROR organisation with coordinates."""
    resp = client.get(ROR_API, params={"affiliation": raw})
    resp.raise_for_status()
    for item in resp.json().get("items", []):
        score = float(item.get("score") or 0.0)
        if score < MIN_CONFIDENCE:
            continue
        org = item.get("organization") or {}
        locations = org.get("addresses") or []
        if not locations:
            continue
        addr = locations[0]
        lat, lon = addr.get("lat"), addr.get("lng")
        if lat is None or lon is None:
            continue
        return {
            "ror": org.get("id"),
            "name": org.get("name"),
            "point": [round(float(lon), 6), round(float(lat), 6)],
            "precision": "institution",
            "confidence": round(score, 3),
        }
    return None


def resolve_place(client: httpx.Client, raw: str) -> dict | None:
    """Geocode one place name to a centroid with an admin-level precision."""
    resp = client.get(
        NOMINATIM_API,
        params={"q": raw, "format": "json", "limit": 1},
        headers=_UA,
    )
    resp.raise_for_status()
    hits = resp.json()
    if not hits:
        return None
    hit = hits[0]
    kind = hit.get("addresstype") or hit.get("type") or ""
    precision = "country" if kind == "country" else "admin1"
    return {
        "point": [round(float(hit["lon"]), 6), round(float(hit["lat"]), 6)],
        "precision": precision,
    }


def _pending_strings(table: dict, strings: list[str]) -> list[str]:
    """Strings not already a key in table, case/whitespace-insensitively,
    deduplicated the same way so a run never adds two case variants of the
    same new key."""
    existing = {k.strip().casefold() for k in table}
    seen: set[str] = set()
    pending = []
    for raw in strings:
        # Affiliation cells sometimes hold several institutions in one string.
        for part in (p.strip() for p in raw.split(";")):
            if not part:
                continue
            key = part.casefold()
            if key in existing or key in seen:
                continue
            seen.add(key)
            pending.append(part)
    return pending


def refresh(
    path: Path,
    strings: list[str],
    resolver: Callable[[httpx.Client, str], dict | None],
    client: httpx.Client,
    *,
    delay: float = 0.0,
    dry_run: bool = False,
) -> None:
    table = load(path)
    pending = _pending_strings(table, strings)

    if not pending:
        print(f"no new entries for {path}, skipping write")
        return

    if dry_run:
        print(f"[dry-run] {path}: {len(pending)} string(s) would be resolved "
              "(no network call made):")
        for part in pending:
            print(f"  ? {part[:70]}")
        return

    changed = False
    for part in pending:
        try:
            result = resolver(client, part)
        except Exception as exc:  # one bad string must not abort the run
            print(f"  ! {part[:60]}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        finally:
            if delay:
                time.sleep(delay)
        table[part] = result
        changed = True
        status = "resolved" if result else "NULL (needs review)"
        print(f"  {status}: {part[:70]}")

    if not changed:
        print(f"no new entries resolved for {path}, skipping write")
        return

    save(path, table)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--affiliations", type=Path,
                        help="file of affiliation strings, one per line")
    parser.add_argument("--places", type=Path, help="file of place names, one per line")
    parser.add_argument("--dry-run", action="store_true",
                        help="print which strings are new without resolving or writing")
    args = parser.parse_args()
    if not args.affiliations and not args.places:
        parser.error("give --affiliations and/or --places")

    with httpx.Client(timeout=30.0, follow_redirects=True, headers=_UA) as client:
        if args.affiliations:
            lines = [
                line.strip()
                for line in args.affiliations.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            print(f"resolving {len(lines)} affiliation strings")
            refresh(INSTITUTIONS, lines, resolve_affiliation, client, dry_run=args.dry_run)
        if args.places:
            lines = [
                line.strip()
                for line in args.places.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            print(f"resolving {len(lines)} place names")
            refresh(
                PLACES, lines, resolve_place, client,
                delay=NOMINATIM_DELAY_SECONDS, dry_run=args.dry_run,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
