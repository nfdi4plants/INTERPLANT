"""Stateless batch loop over ARC identities, sharing pipeline.ingest_arc.

Per-ARC isolation: any failure is recorded on the ArcOutcome and the loop
continues. The DB target is whatever connection the caller injects (None = dry-run).
"""
from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path

from harvester import acquire, dedup, pipeline
from harvester.pipeline import ArcOutcome

logger = logging.getLogger("harvester.batch")

# Per-ARC clone budget in seconds. Named so the CLI default cannot drift from
# this one: the 2026-07-29 full-corpus run lost 4 ARCs to a 60s ceiling that was
# reachable only from Python, and one of them was half of a mirror pair.
DEFAULT_CLONE_TIMEOUT = 60


@dataclass
class BatchReport:
    source: str
    run_timestamp: str
    gitlab_base: str = ""
    outcomes: list[ArcOutcome] = field(default_factory=list)
    verdict: str = "ok"
    verdict_reason: str = ""
    registry: dedup.CollisionRegistry = field(default_factory=dedup.CollisionRegistry)


def _merge_identity(outcome: ArcOutcome, ident: acquire.ArcIdentity) -> ArcOutcome:
    outcome.path = ident.path
    outcome.web_url = ident.web_url
    outcome.project_id = ident.project_id
    outcome.last_activity_at = ident.last_activity_at
    return outcome


def run_batch(
    identities,
    *,
    conn,
    provider: str = "dataplant",
    now_iso: str,
    run_timestamp: str,
    source: str = "live",
    gitlab_base: str = "",
    limit: int | None = None,
    clone_timeout: int = DEFAULT_CLONE_TIMEOUT,
    clone_retries: int = 2,
    parse_timeout: float | None = None,
    apply_filters: bool = False,
) -> BatchReport:
    report = BatchReport(source=source, run_timestamp=run_timestamp, gitlab_base=gitlab_base)
    validator = pipeline.build_validator()

    selected = islice(identities, limit) if limit is not None else identities
    for idx, ident in enumerate(selected, 1):
        logger.info("[%d] %s", idx, ident.path)
        if ident.local_dir is not None:
            outcome = pipeline.ingest_arc(
                Path(ident.local_dir), conn=conn, provider=provider,
                source_uri=ident.web_url, now_iso=now_iso, validator=validator,
                source_etag=ident.last_activity_at or None,
                parse_timeout=parse_timeout,
                apply_filters=apply_filters,
                registry=report.registry,
            )
            report.outcomes.append(_merge_identity(outcome, ident))
            continue

        with tempfile.TemporaryDirectory(prefix="harvest_") as tmp:
            ok, err = acquire.clone_arc(
                ident.web_url, tmp, timeout=clone_timeout, retries=clone_retries,
            )
            if not ok:
                outcome = ArcOutcome(clone_ok=False, clone_error=err)
                logger.warning("  clone FAILED: %s", err)
                report.outcomes.append(_merge_identity(outcome, ident))
                continue
            outcome = pipeline.ingest_arc(
                Path(tmp), conn=conn, provider=provider,
                source_uri=ident.web_url, now_iso=now_iso, validator=validator,
                source_etag=ident.last_activity_at or None,
                parse_timeout=parse_timeout,
                apply_filters=apply_filters,
                registry=report.registry,
            )
            report.outcomes.append(_merge_identity(outcome, ident))

    if not report.outcomes:
        report.verdict = "failed"
        report.verdict_reason = "No ARCs enumerated"
    return report
