"""List public ARC projects on a DataPLANT GitLab instance.

`iter_public_arcs` paginates the GitLab projects API (per_page=100) and yields
only those whose root contains isa.investigation.xlsx. With max_pages=None it
paginates until the API returns an empty page (production use).

Author: Mohamed Abouzid m.abouzid@fz-juelich.de
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass

import httpx

logger = logging.getLogger("harvester.enumerate")

_ISA_PATH = "isa.investigation.xlsx"

# Safety backstop against a misbehaving API that never returns an empty page.
# At per_page=100 this caps enumeration at 100k projects, far above DataPLANT scale.
_MAX_PAGES_CEILING = 1000


@dataclass
class ProbeStats:
    """Counts isa-probe failures across one enumeration pass.

    Owned by the caller: construct one, pass it in, and read `.failures`
    after the iterator is exhausted. `_has_isa` never raises on a probe
    failure and still returns a plain bool - a project that genuinely has
    no isa file must still be excluded normally - so this counter is the
    only way for a caller to tell "excluded because GitLab said no" apart
    from "excluded because GitLab did not answer". The distinction matters
    once a caller treats a missing project as deleted (see publish.swap):
    a transient probe failure must never be mistaken for that.
    """

    failures: int = 0


def iter_public_arcs(
    base_url: str, *, max_pages: int | None = None, stats: ProbeStats | None = None
) -> Iterator[dict]:
    """Yield project descriptors for public projects whose root contains isa.investigation.xlsx.

    max_pages=None paginates until the API returns an empty page (production use),
    bounded by a safety ceiling; pass an integer to cap pages (tests).

    `stats`, if given, is incremented in place on every isa-probe failure
    (network error or timeout, not a genuine absence of the file). Pass one
    when the caller needs to distinguish a transient GitLab hiccup from a
    real enumeration change.
    """
    if stats is None:
        stats = ProbeStats()
    last_page = max_pages if max_pages is not None else _MAX_PAGES_CEILING
    with httpx.Client(base_url=base_url, timeout=15.0) as client:
        for page in range(1, last_page + 1):
            resp = client.get(
                "/api/v4/projects",
                params={"visibility": "public", "archived": "false", "per_page": 100, "page": page},
            )
            resp.raise_for_status()
            projects = resp.json()
            if not projects:
                return
            for project in projects:
                if _has_isa(client, project, stats):
                    yield {
                        "project_id": project["id"],
                        "path_with_namespace": project["path_with_namespace"],
                        "default_branch": project.get("default_branch"),
                        "web_url": project["web_url"],
                        "last_activity_at": project.get("last_activity_at"),
                    }
        else:
            if max_pages is None:
                logger.warning(
                    "iter_public_arcs hit the %d-page safety ceiling; results may be truncated",
                    _MAX_PAGES_CEILING,
                )


def _has_isa(client: httpx.Client, project: dict, stats: ProbeStats) -> bool:
    branch = project.get("default_branch")
    if not branch:
        return False
    path = f"/api/v4/projects/{project['id']}/repository/files/{_ISA_PATH}/raw"
    try:
        resp = client.head(path, params={"ref": branch}, follow_redirects=True)
    except httpx.HTTPError as exc:
        stats.failures += 1
        logger.warning("isa probe failed for %s: %s", project["path_with_namespace"], exc)
        return False
    if resp.status_code == 200:
        return True
    # Some GitLab instances reject HEAD on raw-file endpoints. Fall back to a GET
    # with a tiny range header so we don't pull the whole file.
    if resp.status_code in (404, 405):
        try:
            resp = client.get(
                path,
                params={"ref": branch},
                headers={"Range": "bytes=0-1"},
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            stats.failures += 1
            logger.warning("isa GET probe failed for %s: %s", project["path_with_namespace"], exc)
            return False
        return resp.status_code in (200, 206)
    return False
