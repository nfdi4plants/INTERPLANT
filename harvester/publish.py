"""Decide whether a staged corpus may replace the published one, and swap it.

The gate is deliberately pure - no database, no clock - because it is the part
whose failure cases matter most and must be cheap to test. AWI takes a full dump
of whatever public.records holds and expires entries on a 5-day TTL, so
publishing a truncated corpus deletes real records from the portal.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_FLOOR_RATIO = 0.9

# An absolute floor, independent of the previous publish. The ratio alone
# ratchets: seven nights each staging 90% of the last publish take 144 records
# down to 66, with every night individually passing, and the portal's 5-day TTL
# follows it all the way down. The ratio catches a cliff; this catches a slide.
# 120 is about 83% of the verified 144-record corpus. Raise it as the corpus
# grows; override per run with --min-records.
DEFAULT_MIN_RECORDS = 120


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
    min_records: int = DEFAULT_MIN_RECORDS,
) -> GateResult:
    """Four independent checks, cheapest and most damaging first.

    staged_count, reported_upserts and published_count are all record (row)
    counts, never project or ARC counts. Passing a project count where a
    record count belongs will set the floor from the wrong number and can
    refuse every future publish.

    This gate is cardinality-only: it never inspects the staged rows'
    content. A corpus of the right size but with degenerate payloads, or
    whose record ids have all changed shape, passes every check here. Guarding
    against that needs a separate id-overlap check against the published set,
    which this gate does not perform.
    """
    if not 0 < floor_ratio <= 1:
        raise ValueError(f"floor_ratio must be in (0, 1], got {floor_ratio!r}")
    if min_records < 0:
        raise ValueError(f"min_records must not be negative, got {min_records!r}")

    if staged_count <= 0:
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

    if staged_count < min_records:
        return GateResult(
            False,
            f"staged {staged_count} rows, below the absolute minimum of "
            f"{min_records}; a relative floor alone would let repeated small "
            "losses ratchet the corpus down unrefused",
        )

    return GateResult(
        True, f"staged {staged_count} rows, floor {floor}, minimum {min_records}"
    )
