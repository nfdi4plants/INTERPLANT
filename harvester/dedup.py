"""Resolve several ARCs claiming one record id.

The same investigation is often published under both a consortium namespace and
a personal one (ceplas/TGA_Basu26 and sbasu1/TGA_Basu26). Those mirrors are one
dataset and must collapse to one record - but the collapse has to be a stated
policy, not whichever ARC the enumeration happened to reach last.

Preference order is spec 3.4: has DOI > most recent activity > lexicographically
first namespace > lexicographically first unique_id. unique_id is a uuid5 over
the ARC source uri, so it is the only signal here that is unique per ARC,
which is what makes the order total and the winner independent of arrival
order.

Author: Mohamed Abouzid m.abouzid@fz-juelich.de
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from harvester import ids


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

    Total order with no ties (unique_id is unique per ARC), which is what
    makes the batch result independent of enumeration order.
    """
    if incoming.has_doi != existing.has_doi:
        return incoming.has_doi

    # last_activity_at is ISO-8601 UTC, so lexicographic order is chronological.
    if incoming.last_activity_at != existing.last_activity_at:
        return incoming.last_activity_at > existing.last_activity_at

    if incoming.namespace != existing.namespace:
        return incoming.namespace < existing.namespace

    # Namespace is NOT unique per ARC: two repos in one namespace can carry the
    # same investigation identifier. uniqueId is a uuid5 over the ARC source
    # uri, so it is the only signal here that is unique per ARC, which is what
    # makes this order total rather than merely near-total.
    return incoming.unique_id < existing.unique_id


@dataclass(frozen=True)
class Resolution:
    """What the pipeline should do with a candidate that reached the registry."""

    action: str  # "insert" | "replace" | "suppress" | "disambiguate"
    record_id: str
    suppressed_by: str = ""


class CollisionRegistry:
    """Per-run winner table for record ids.

    Stateful on purpose: it holds the winning candidate AND that ARC's outcome
    so a later, stronger mirror can retroactively mark the displaced one
    suppressed. Without that back-reference the audit report would show two
    ARCs upserted under one id and the funnel would not add up.

    In-memory rather than DB-backed so dry runs (conn=None) exercise exactly the
    same resolution path as a real harvest. The real run starts from an empty
    table, so there is no prior state to reconcile against.
    """

    def __init__(self) -> None:
        self._winners: dict[str, tuple[Candidate, object]] = {}
        self.reviews: list[tuple[Candidate, Candidate, str]] = []

    def winner(self, record_id: str) -> Candidate | None:
        entry = self._winners.get(record_id)
        return entry[0] if entry else None

    def resolve(self, candidate: Candidate, outcome) -> Resolution:
        entry = self._winners.get(candidate.record_id)
        if entry is None:
            self._winners[candidate.record_id] = (candidate, outcome)
            return Resolution("insert", candidate.record_id)

        held, held_outcome = entry

        if ids.normalize(candidate.title) != ids.normalize(held.title):
            # Not a mirror: two different datasets sharing an investigation
            # identifier. Keep both - a visible duplicate is always better than
            # silent loss - and flag the pair for a human.
            new_id = ids.disambiguate_id(candidate.record_id, candidate.unique_id)
            self.reviews.append((held, candidate, new_id))
            return Resolution("disambiguate", new_id)

        if prefer(candidate, held):
            held_outcome.suppressed_by = candidate.namespace
            held_outcome.upsert_ok = False
            self._winners[candidate.record_id] = (candidate, outcome)
            return Resolution("replace", candidate.record_id)

        return Resolution("suppress", candidate.record_id, suppressed_by=held.namespace)
