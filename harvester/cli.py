"""Harvester CLI. Usage:

    python -m harvester ingest <arc-path> [--dsn DSN] [--provider PROVIDER]

The CLI orchestrates: IsaReader -> classifier -> build_record -> validate -> upsert.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from harvester import acquire, audit, batch, db, pipeline

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
    )
    json_path, md_path = audit.write_run_report(report, args.out_dir)
    logger.info("Audit report: %s (json: %s)", md_path, json_path)

    if report.verdict != "ok":
        logger.error("Harvest verdict: %s (%s)", report.verdict, report.verdict_reason)
        return 1
    return 0


def _redact(dsn: str) -> str:
    if "://" in dsn and "@" in dsn:
        head, rest = dsn.split("://", 1)
        creds, tail = rest.split("@", 1)
        return f"{head}://***@{tail}"
    return dsn
