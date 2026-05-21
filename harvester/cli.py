"""Harvester CLI. Usage:

    python -m harvester ingest <arc-path> [--dsn DSN] [--provider PROVIDER]

The CLI orchestrates: IsaReader -> classifier -> build_record -> validate -> upsert.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from harvester import db
from harvester.build import build_record
from harvester.classifiers.omics import classify_omics
from harvester.isa_reader import IsaReader

logger = logging.getLogger("harvester")

DEFAULT_DSN = "postgresql://interplant:interplant@localhost:5432/interplant"
SCHEMAS_DIR = Path(__file__).parent.parent / "docs" / "specs" / "schemas"


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
    investigation = IsaReader().read(arc_path)

    omics_by_folder = _classify_assays(investigation)

    now_iso = datetime.now(tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    # file:// placeholder; Plan 4 replaces with GitLab URL.
    arc_source_uri = arc_path.resolve().as_uri()

    record = build_record(
        investigation,
        omics_by_folder,
        arc_source_uri=arc_source_uri,
        harvested_at=now_iso,
        created=now_iso,
        updated=now_iso,
        provider=provider,
    )
    _validate(record)

    logger.info("Connecting to %s", _redact(dsn))
    conn = db.connect(dsn)
    db.apply_schema(conn)
    db.upsert_record(conn, record["id"], record)
    logger.info("Upserted record %s", record["id"])
    return 0


def _classify_assays(investigation) -> dict[str, str]:
    out: dict[str, str] = {}
    for study in investigation.studies:
        for assay in study.assays:
            domain = classify_omics(assay.folder)
            if domain is not None:
                out[assay.folder] = domain
    return out


def _validate(record: dict) -> None:
    record_schema = json.loads((SCHEMAS_DIR / "record.schema.json").read_text("utf-8"))
    assay_ext = json.loads((SCHEMAS_DIR / "assay-extensions.schema.json").read_text("utf-8"))
    registry = Registry().with_resource(
        "https://interplant.org/schemas/assay-extensions.schema.json",
        Resource.from_contents(assay_ext),
    )
    Draft202012Validator(
        record_schema,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    ).validate(record)


def _redact(dsn: str) -> str:
    if "://" in dsn and "@" in dsn:
        head, rest = dsn.split("://", 1)
        creds, tail = rest.split("@", 1)
        return f"{head}://***@{tail}"
    return dsn
