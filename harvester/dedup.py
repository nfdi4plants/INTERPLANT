"""Resolve several ARCs claiming one record id.

The same investigation is often published under both a consortium namespace and
a personal one (ceplas/TGA_Basu26 and sbasu1/TGA_Basu26). Those mirrors are one
dataset and must collapse to one record - but the collapse has to be a stated
policy, not whichever ARC the enumeration happened to reach last.

Preference order is spec 3.4: has DOI > most recent activity > lexicographically
first namespace. Namespace is unique per ARC, so the order is total and the
winner never depends on arrival order.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Candidate:
    """The signals the preference order needs, all read from a built record."""

    record_id: str
    title: str
    has_doi: bool
    last_activity_at: str
    namespace: str
    unique_id: str


def namespace_of(arc_source_uri: str) -> str:
    """Everything in the GitLab path except the repository segment itself."""
    path = urlsplit(arc_source_uri).path.strip("/")
    parts = [p for p in path.split("/") if p]
    return "/".join(parts[:-1]) if len(parts) > 1 else ""


def candidate_from_record(record: dict, *, last_activity_at: str) -> Candidate:
    props = record["properties"]
    return Candidate(
        record_id=record["id"],
        title=props.get("title", ""),
        has_doi=any("doi" in pub for pub in props.get("publications", [])),
        last_activity_at=last_activity_at or "",
        namespace=namespace_of(props.get("arc_source_uri", "")),
        unique_id=props.get("uniqueId", ""),
    )


def prefer(incoming: Candidate, existing: Candidate) -> bool:
    """True if `incoming` should replace `existing` as the record for this id.

    Total order with no ties (namespace is unique per ARC), which is what makes
    the batch result independent of enumeration order.
    """
    if incoming.has_doi != existing.has_doi:
        return incoming.has_doi

    # last_activity_at is ISO-8601 UTC, so lexicographic order is chronological.
    if incoming.last_activity_at != existing.last_activity_at:
        return incoming.last_activity_at > existing.last_activity_at

    # Same ARC seen twice: keep the incumbent rather than churn the row.
    if incoming.namespace == existing.namespace:
        return False

    return incoming.namespace < existing.namespace
