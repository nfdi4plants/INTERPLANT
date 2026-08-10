"""Record-id minting. Convention is `<provider>-<slug>` where slug is normalized.

The exact convention is provisional (see open_questions.md). Keep this rule
isolated so it can be swapped in one place when AWI confirms the format.
"""
from __future__ import annotations

import re

_SLUG_NON_ALPHANUM = re.compile(r"[^a-z0-9]+")


def normalize(value: str) -> str:
    lowered = value.lower()
    return _SLUG_NON_ALPHANUM.sub("-", lowered).strip("-")


def mint_id(provider: str, slug: str) -> str:
    """Return the record id for an ARC.

    Raises ValueError if either argument is empty after normalization.
    """
    if not provider:
        raise ValueError("provider must be non-empty")
    if not slug:
        raise ValueError("slug must be non-empty")
    normalized_slug = normalize(slug)
    if not normalized_slug:
        raise ValueError(f"slug normalized to empty string: {slug!r}")
    return f"{provider}-{normalized_slug}"


def disambiguate_id(record_id: str, unique_id: str) -> str:
    """Return a collision-free variant of `record_id` for a non-mirror ARC.

    Suffix is the first 6 hex chars of the record's uniqueId (a uuid5 over the
    ARC source URI), so the result is stable across runs rather than depending
    on enumeration order. uuid strings are lowercase hex, which keeps the id
    inside the schema pattern `^[a-z0-9][a-z0-9-]*$`.
    """
    suffix = unique_id.replace("-", "")[:6]
    if not suffix:
        raise ValueError(f"unique_id yielded no suffix: {unique_id!r}")
    return f"{record_id}-{suffix}"
