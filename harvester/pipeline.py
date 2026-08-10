"""Shared single-ARC pipeline: parse -> classify -> build -> validate -> upsert.

This is the ONE definition of the per-ARC pipeline, consumed by both the single
`ingest` CLI command and the batch loop. Upsert happens only when a connection is
supplied; with conn=None the pipeline runs through validation and stops (dry-run).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from harvester import db, dedup, filters, timeouts
from harvester.build import build_record
from harvester.classifiers.omics import classify_omics
from harvester.isa_reader import IsaReader

SCHEMAS_DIR = Path(__file__).parent.parent / "docs" / "specs" / "schemas"


@dataclass
class ArcOutcome:
    path: str = ""
    web_url: str = ""
    project_id: int = 0
    last_activity_at: str = ""
    clone_ok: bool = False
    clone_error: str = ""
    parse_ok: bool = False
    parse_error: str = ""
    parse_exc_type: str = ""
    filtered: bool = False
    filter_rule: str = ""
    build_ok: bool = False
    build_error: str = ""
    validate_ok: bool = False
    validate_errors: list[str] = field(default_factory=list)
    upsert_ok: bool = False
    upsert_error: str = ""
    record_id: str = ""
    title: str = ""
    suppressed_by: str = ""
    disambiguated_to: str = ""
    n_studies: int = 0
    n_assays: int = 0
    omics_classified: int = 0
    omics_total: int = 0


def build_validator() -> Draft202012Validator:
    record_schema = json.loads((SCHEMAS_DIR / "record.schema.json").read_text("utf-8"))
    assay_ext = json.loads((SCHEMAS_DIR / "assay-extensions.schema.json").read_text("utf-8"))
    registry = Registry().with_resource(
        "https://interplant.org/schemas/assay-extensions.schema.json",
        Resource.from_contents(assay_ext),
    )
    return Draft202012Validator(
        record_schema,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def _classify_assays(investigation) -> tuple[dict[str, str], int, int]:
    out: dict[str, str] = {}
    seen: set[str] = set()
    n_total = 0
    n_classified = 0
    for study in investigation.studies:
        for assay in study.assays:
            if assay.folder in seen:
                continue
            seen.add(assay.folder)
            n_total += 1
            domain = classify_omics(
                assay.folder,
                assay.measurement_type,
                technology_type=assay.technology_type,
                technology_platform=getattr(assay, "technology_platform", None),
            )
            if domain is not None:
                out[assay.folder] = domain
                n_classified += 1
    return out, n_classified, n_total


def ingest_arc(
    arc_path,
    *,
    conn,
    provider: str = "dataplant",
    source_uri: str,
    now_iso: str,
    validator: Draft202012Validator,
    source_etag: str | None = None,
    parse_timeout: float | None = None,
    apply_filters: bool = False,
    registry: dedup.CollisionRegistry | None = None,
) -> ArcOutcome:
    """Run one ARC through the pipeline. Never raises on bad data; records the failure.

    `parse_timeout` bounds the arctrl parse in seconds; None means no limit.
    `apply_filters` enables the policy exclusions in filters.py; off by default so
    single-ARC ingests and fixture tests are unaffected.
    """
    out = ArcOutcome(clone_ok=True)

    guard = timeouts.TimeoutState()
    try:
        with timeouts.parse_timeout(parse_timeout, state=guard):
            investigation = IsaReader().read(arc_path)
        out.parse_ok = True
    except Exception as exc:  # noqa: BLE001 - any arctrl failure is captured per-ARC
        # arctrl wraps our ParseTimeout into a generic error, so trust the flag
        # over the exception type to keep timeouts distinct in the audit report.
        out.parse_exc_type = "ParseTimeout" if guard.fired else type(exc).__name__
        out.parse_error = str(exc)[:300]
        return out

    if apply_filters:
        verdict = filters.evaluate(investigation)
        if verdict.excluded:
            out.filtered = True
            out.filter_rule = verdict.rule
            return out

    out.n_studies = len(investigation.studies)
    out.n_assays = sum(len(s.assays) for s in investigation.studies)
    omics_by_folder, n_classified, n_total = _classify_assays(investigation)
    out.omics_classified = n_classified
    out.omics_total = n_total

    try:
        record = build_record(
            investigation,
            omics_by_folder,
            arc_source_uri=source_uri,
            harvested_at=now_iso,
            created=now_iso,
            updated=now_iso,
            provider=provider,
        )
        out.build_ok = True
        out.record_id = record["id"]
    except Exception as exc:  # noqa: BLE001
        out.build_error = f"{type(exc).__name__}: {exc}"
        return out

    out.validate_errors = [
        f"{'.'.join(str(p) for p in err.absolute_path) or '(root)'}: {err.message[:200]}"
        for err in validator.iter_errors(record)
    ]
    out.validate_ok = not out.validate_errors
    if not out.validate_ok:
        return out

    if registry is not None:
        candidate = dedup.candidate_from_record(record, last_activity_at=source_etag or "")
        out.title = candidate.title
        resolution = registry.resolve(candidate, out)
        if resolution.action == "suppress":
            out.suppressed_by = resolution.suppressed_by
            return out
        if resolution.action == "disambiguate":
            record = {**record, "id": resolution.record_id}
            out.record_id = resolution.record_id
            out.disambiguated_to = resolution.record_id

    if conn is not None:
        try:
            db.upsert_record(conn, record["id"], record, source_etag=source_etag)
            out.upsert_ok = True
        except Exception as exc:  # noqa: BLE001
            out.upsert_error = f"{type(exc).__name__}: {exc}"

    return out
