"""Decide whether a staged corpus may replace the published one, and swap it.

The gate is deliberately pure - no database, no clock - because it is the part
whose failure cases matter most and must be cheap to test. AWI takes a full dump
of whatever public.records holds and expires entries on a 5-day TTL, so
publishing a truncated corpus deletes real records from the portal.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_FLOOR_RATIO = 0.9


@dataclass(frozen=True)
class GateResult:
    ok: bool
    reason: str


def evaluate(
    *,
    staged_count: int,
    reported_upserts: int,
    published_count: int,
    floor_ratio: float = DEFAULT_FLOOR_RATIO,
) -> GateResult:
    """Three independent checks, cheapest and most damaging first.

    staged_count, reported_upserts and published_count are all record (row)
    counts, never project or ARC counts. Passing a project count where a
    record count belongs will set the floor from the wrong number and can
    refuse every future publish.
    """
    if staged_count == 0:
        return GateResult(False, "staged corpus is empty; refusing to publish nothing")

    if staged_count != reported_upserts:
        return GateResult(
            False,
            f"staged {staged_count} rows but the run report claims "
            f"{reported_upserts} upserts; the database and the report disagree",
        )

    floor = int(published_count * floor_ratio)
    if staged_count < floor:
        return GateResult(
            False,
            f"staged {staged_count} rows, below the floor of {floor} "
            f"({floor_ratio:.0%} of the published {published_count}); "
            "this looks like a failed harvest, not a shrunken corpus",
        )

    return GateResult(True, f"staged {staged_count} rows, floor {floor}")
