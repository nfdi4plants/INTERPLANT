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
# grows; override per run with --min-records. Raising it is deliberately not
# free: test_healthy_run_passes pins the success message ("minimum 120") and
# test_the_floor_is_inclusive pins the 129/128 boundary, so moving this
# constant trips tests on purpose and forces a human to review the change.
DEFAULT_MIN_RECORDS = 120

# Machine-readable verdict kinds. Tests and callers branch on these; `reason`
# is prose for humans and must never be load-bearing. Two fix rounds were spent
# on collisions between refusal messages and tests that substring-matched them.
KIND_OK = "ok"
KIND_EMPTY = "empty"
KIND_MISMATCH = "mismatch"
KIND_FLOOR = "floor"
KIND_MINIMUM = "minimum"


@dataclass(frozen=True)
class GateResult:
    ok: bool
    reason: str
    kind: str


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
        return GateResult(
            False, "staged corpus is empty; refusing to publish nothing", KIND_EMPTY
        )

    if staged_count != reported_upserts:
        return GateResult(
            False,
            f"staged {staged_count} rows but the run report claims "
            f"{reported_upserts} upserts; the database and the report disagree",
            KIND_MISMATCH,
        )

    floor = int(published_count * floor_ratio)
    if staged_count < floor:
        return GateResult(
            False,
            f"staged {staged_count} rows, below the floor of {floor} "
            f"({floor_ratio:.0%} of the published {published_count}); "
            "this looks like a failed harvest, not a shrunken corpus",
            KIND_FLOOR,
        )

    if staged_count < min_records:
        return GateResult(
            False,
            f"staged {staged_count} rows, below the absolute minimum of "
            f"{min_records} (override with min_records=); a relative threshold "
            "alone cannot catch repeated small losses, nor protect a table that "
            "is already empty",
            KIND_MINIMUM,
        )

    return GateResult(
        True,
        f"staged {staged_count} rows, floor {floor}, minimum {min_records}",
        KIND_OK,
    )


def swap(conn, *, enumeration: dict[str, str]) -> int:
    """Replace the published corpus and the enumeration snapshot atomically.

    Readers see the old corpus or the new one, never a mixture: TRUNCATE takes
    an ACCESS EXCLUSIVE lock, held for milliseconds at this scale. The snapshot
    advances in the same transaction as the records, so a rolled-back swap also
    leaves the snapshot behind and the next run retries the same change.
    """
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("TRUNCATE public.records")
            # Columns named explicitly: a positional SELECT * would silently
            # transpose values if the two table definitions ever drift, and
            # id/source_etag are both text so Postgres would not reject it.
            cur.execute(
                "INSERT INTO public.records (id, payload, source_etag, ingested_at) "
                "SELECT id, payload, source_etag, ingested_at FROM staging.records"
            )
            cur.execute("TRUNCATE public.published_projects")
            if enumeration:
                cur.executemany(
                    "INSERT INTO public.published_projects "
                    "(project_path, last_activity_at) VALUES (%s, %s)",
                    list(enumeration.items()),
                )
            cur.execute("SELECT count(*) FROM public.records")
            return cur.fetchone()[0]
