"""Harvester CLI. Usage:

    python -m harvester ingest <arc-path> [--dsn DSN] [--provider PROVIDER]
    python -m harvester harvest --source live [--dry-run] [--dsn DSN]
    python -m harvester refresh [--dsn DSN] [--max-age-days N] [--force]

`harvest` always harvests and writes straight to public.records. `refresh` is
the production entry point: it harvests only when the GitLab enumeration
changed, stages the result, and publishes it atomically behind a gate.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg

from harvester import acquire, audit, batch, db, detect, pipeline, publish

logger = logging.getLogger("harvester")

DEFAULT_DSN = "postgresql://interplant:interplant@localhost:5432/interplant"


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_usage(sys.stderr)
        return 2
    if args.command == "ingest":
        return _ingest(Path(args.arc_path), dsn=args.dsn, provider=args.provider)
    if args.command == "harvest":
        return _harvest(args)
    if args.command == "refresh":
        return _refresh(args)
    parser.print_usage(sys.stderr)
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harvester")
    sub = parser.add_subparsers(dest="command")
    ingest = sub.add_parser("ingest", help="Ingest a single ARC into Postgres")
    ingest.add_argument("arc_path", help="Path to the ARC root directory")
    ingest.add_argument(
        "--dsn",
        default=os.environ.get("INTERPLANT_PG_DSN", DEFAULT_DSN),
        help="Postgres DSN (env INTERPLANT_PG_DSN, else local default)",
    )
    ingest.add_argument(
        "--provider",
        default="dataplant",
        help="Record-id provider prefix (default: dataplant)",
    )
    harvest = sub.add_parser("harvest", help="Batch-harvest many ARCs into Postgres")
    src = harvest.add_mutually_exclusive_group(required=True)
    src.add_argument("--source", choices=["live"], help="Enumerate + clone live ARCs")
    src.add_argument("--local-dir", help="Harvest ARC subdirectories under this path")
    harvest.add_argument("--gitlab-base", default="https://git.nfdi4plants.org")
    harvest.add_argument("--dsn", default=None, help="Postgres DSN (omit with --dry-run)")
    harvest.add_argument("--dry-run", action="store_true", help="Validate only, no DB writes")
    harvest.add_argument("--out-dir", default="./harvest-runs")
    harvest.add_argument("--limit", type=int, default=None)
    harvest.add_argument("--provider", default="dataplant")
    harvest.add_argument(
        "--parse-timeout",
        type=int,
        default=None,
        help=(
            "Per-ARC parse budget in seconds (default: no limit). An ARC that "
            "exceeds it is recorded as a ParseTimeout failure and the run continues."
        ),
    )
    harvest.add_argument(
        "--clone-timeout",
        type=int,
        default=batch.DEFAULT_CLONE_TIMEOUT,
        help=(
            "Per-ARC git clone budget in seconds (default: "
            f"{batch.DEFAULT_CLONE_TIMEOUT}). Raise it for large repositories; "
            "an ARC that exceeds it never reaches parse, so a mirror of it "
            "cannot be deduped against."
        ),
    )
    harvest.add_argument(
        "--no-filter",
        action="store_true",
        help=(
            "Skip the template/placeholder exclusions. Filtering is ON for "
            "harvests; this is the escape hatch for diagnosing what got dropped."
        ),
    )
    refresh = sub.add_parser(
        "refresh",
        help="Harvest and publish only when the GitLab enumeration changed",
    )
    refresh.add_argument("--gitlab-base", default="https://git.nfdi4plants.org")
    refresh.add_argument(
        "--dsn",
        default=os.environ.get("INTERPLANT_PG_DSN", DEFAULT_DSN),
        help="Postgres DSN (env INTERPLANT_PG_DSN, else local default)",
    )
    refresh.add_argument("--out-dir", default="./harvest-runs")
    refresh.add_argument("--provider", default="dataplant")
    refresh.add_argument(
        "--max-age-days",
        type=int,
        default=7,
        help=(
            "Harvest unconditionally when the last publish is older than this, "
            "even with no detected change (default: 7). GitLab's "
            "last_activity_at can miss an edit; this is the backstop."
        ),
    )
    refresh.add_argument(
        "--force", action="store_true", help="Harvest regardless of the diff"
    )
    refresh.add_argument(
        "--min-records",
        type=int,
        default=publish.DEFAULT_MIN_RECORDS,
        help=(
            "Absolute floor on the published record count (default: "
            f"{publish.DEFAULT_MIN_RECORDS}). The relative floor alone lets "
            "repeated small losses ratchet the corpus down with every night "
            "passing; this is the backstop. Raise it as the corpus grows."
        ),
    )
    refresh.add_argument(
        "--parse-timeout",
        type=int,
        default=None,
        help=(
            "Per-ARC parse budget in seconds (default: no limit). An ARC that "
            "exceeds it is recorded as a ParseTimeout failure and the run continues."
        ),
    )
    refresh.add_argument(
        "--clone-timeout", type=int, default=batch.DEFAULT_CLONE_TIMEOUT
    )
    return parser


def _ingest(arc_path: Path, *, dsn: str, provider: str) -> int:
    if not arc_path.exists():
        logger.error("ARC path does not exist: %s", arc_path)
        return 1
    if not arc_path.is_dir():
        logger.error("ARC path is not a directory: %s", arc_path)
        return 1

    logger.info("Parsing ARC at %s", arc_path)
    now_iso = _now_iso()
    source_uri = arc_path.resolve().as_uri()
    validator = pipeline.build_validator()

    logger.info("Connecting to %s", _redact(dsn))
    conn = db.connect(dsn)
    db.apply_schema(conn)

    outcome = pipeline.ingest_arc(
        arc_path,
        conn=conn,
        provider=provider,
        source_uri=source_uri,
        now_iso=now_iso,
        validator=validator,
    )
    if not outcome.parse_ok:
        logger.error("Parse failed (%s): %s", outcome.parse_exc_type, outcome.parse_error)
        return 1
    if not outcome.build_ok:
        logger.error("Build failed: %s", outcome.build_error)
        return 1
    if not outcome.validate_ok:
        logger.error("Validation failed: %s", "; ".join(outcome.validate_errors[:5]))
        return 1
    logger.info("Upserted record %s", outcome.record_id)
    return 0


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _harvest(args) -> int:
    if args.dry_run and args.dsn:
        logger.error("--dry-run and --dsn are mutually exclusive")
        return 2

    now_iso = _now_iso()
    run_timestamp = now_iso.replace("-", "").replace(":", "")  # 20260622T000000Z

    if args.local_dir:
        local_dir = Path(args.local_dir)
        if not local_dir.exists():
            logger.error("Local directory does not exist: %s", local_dir)
            return 1
        if not local_dir.is_dir():
            logger.error("Local path is not a directory: %s", local_dir)
            return 1
        identities = acquire.iter_local_arcs(args.local_dir)
        source = "local"
        gitlab_base = ""
    else:
        identities = acquire.iter_live_arcs(args.gitlab_base)
        source = "live"
        gitlab_base = args.gitlab_base

    conn = None
    if not args.dry_run:
        dsn = args.dsn or os.environ.get("INTERPLANT_PG_DSN", DEFAULT_DSN)
        logger.info("Connecting to %s", _redact(dsn))
        try:
            conn = db.connect(dsn)
            db.apply_schema(conn)
        except Exception as exc:  # noqa: BLE001
            logger.error("Cannot connect to DB: %s", exc)
            return 1

    report = batch.run_batch(
        identities, conn=conn, provider=args.provider, now_iso=now_iso,
        run_timestamp=run_timestamp, source=source, gitlab_base=gitlab_base,
        limit=args.limit, parse_timeout=args.parse_timeout,
        clone_timeout=args.clone_timeout,
        apply_filters=not args.no_filter,
    )
    json_path, md_path = audit.write_run_report(report, args.out_dir)
    logger.info("Audit report: %s (json: %s)", md_path, json_path)

    if report.verdict != "ok":
        logger.error("Harvest verdict: %s (%s)", report.verdict, report.verdict_reason)
        return 1
    return 0


def _refresh(args) -> int:
    """Enumerate, decide, harvest, gate, publish.

    Enumeration happens once and the identities are reused for the harvest, so
    the per-project isa.investigation.xlsx probe is not paid twice.
    """
    logger.info("Connecting to %s", _redact(args.dsn))
    # Bootstrap on an unqualified connection first. db.connect(schema="staging")
    # verifies staging.records already exists before it will set search_path,
    # so calling it before apply_schema has ever run refuses to connect on a
    # fresh database. apply_schema's DDL is fully schema-qualified, so it
    # creates both schemas' tables regardless of which one is on search_path.
    try:
        bootstrap_conn = db.connect(args.dsn)
    except Exception as exc:  # noqa: BLE001
        logger.error("Cannot connect to DB: %s", exc)
        return 1
    try:
        db.apply_schema(bootstrap_conn)
    except Exception as exc:  # noqa: BLE001
        logger.error("Cannot apply schema: %s", exc)
        return 1
    finally:
        bootstrap_conn.close()

    try:
        conn = db.connect(args.dsn, schema="staging")
    except Exception as exc:  # noqa: BLE001
        logger.error("Cannot connect to DB: %s", exc)
        return 1

    logger.info("Enumerating %s", args.gitlab_base)
    identities = list(acquire.iter_live_arcs(args.gitlab_base))
    live = {ident.path: ident.last_activity_at for ident in identities}
    logger.info("Enumerated %d ARCs", len(live))

    published = db.read_published_projects(conn)
    diff = detect.diff_enumeration(live, published)
    last_published = db.last_published_at(conn)
    stale = last_published is None or (
        datetime.now(tz=UTC) - last_published >= timedelta(days=args.max_age_days)
    )

    if diff.is_empty and not stale and not args.force:
        logger.info("No enumeration change and the last publish is recent; nothing to do")
        return 0

    reason = "forced" if args.force else ("stale snapshot" if diff.is_empty else diff.summary())
    logger.info("Harvesting: %s", reason)
    # Name the projects, not just the counts. At 3am the useful question is which
    # ARC moved, and the enumeration is the only place that answer exists: the
    # harvest that follows is whole-corpus and cannot tell you.
    for label, paths in (
        ("appeared", diff.appeared),
        ("vanished", diff.vanished),
        ("changed", diff.changed),
    ):
        if paths:
            logger.info("  %s: %s", label, ", ".join(paths))

    now_iso = _now_iso()
    run_timestamp = now_iso.replace("-", "").replace(":", "")

    db.truncate_staging(conn)
    report = batch.run_batch(
        iter(identities), conn=conn, provider=args.provider, now_iso=now_iso,
        run_timestamp=run_timestamp, source="live", gitlab_base=args.gitlab_base,
        parse_timeout=args.parse_timeout, clone_timeout=args.clone_timeout,
        apply_filters=True,
    )
    json_path, md_path = audit.write_run_report(report, args.out_dir)
    logger.info("Audit report: %s (json: %s)", md_path, json_path)

    if report.verdict != "ok":
        logger.error("Harvest verdict: %s (%s)", report.verdict, report.verdict_reason)
        logger.error("Refusing to publish; public.records is untouched")
        return 1

    staged = db.count_records(conn, schema="staging")
    # published_count must be the RECORD count, not len(published). The snapshot
    # holds one entry per enumerated project (~213), while the corpus holds one
    # row per surviving record (~144) after template exclusions and mirror dedup.
    # Passing the project count would set the floor to int(213*0.9)=191 and refuse
    # every publish forever.
    gate = publish.evaluate(
        staged_count=staged,
        reported_upserts=audit.aggregate(report)["n_upserted"],
        published_count=db.count_records(conn, schema="public"),
        min_records=args.min_records,
    )
    if not gate.ok:
        logger.error("Publish gate refused: %s", gate.reason)
        logger.error("public.records is untouched; see %s", md_path)
        return 1

    try:
        count = publish.swap(conn, enumeration=live)
    except psycopg.errors.LockNotAvailable:
        # The swap sets lock_timeout=5s, so a reader holding ACCESS SHARE on
        # public.records makes TRUNCATE give up rather than queue behind it and
        # stall the endpoint. The transaction rolled back, so the published
        # corpus is intact and staging still holds tonight's harvest.
        logger.error(
            "Could not acquire the table lock within 5s; a reader was holding it. "
            "public.records is untouched and the harvest is preserved in staging. "
            "The next run will retry."
        )
        return 1
    logger.info("Published %d records (%s)", count, gate.reason)
    return 0


def _redact(dsn: str) -> str:
    if "://" in dsn and "@" in dsn:
        head, rest = dsn.split("://", 1)
        creds, tail = rest.split("@", 1)
        return f"{head}://***@{tail}"
    return dsn
