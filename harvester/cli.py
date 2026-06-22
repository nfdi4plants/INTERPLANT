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

from harvester import db, pipeline

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


def _redact(dsn: str) -> str:
    if "://" in dsn and "@" in dsn:
        head, rest = dsn.split("://", 1)
        creds, tail = rest.split("@", 1)
        return f"{head}://***@{tail}"
    return dsn
