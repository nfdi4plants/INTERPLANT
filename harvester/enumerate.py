"""List public ARC projects on a DataPLANT GitLab instance.

The skeleton uses this only via its env-gated test. Production use (pagination
completeness, retry, audit logging) is deferred to Plan 4.
"""
from __future__ import annotations

import logging
from typing import Iterator

import httpx

logger = logging.getLogger("harvester.enumerate")

_ISA_PATH = "isa.investigation.xlsx"


def iter_public_arcs(base_url: str, *, max_pages: int = 5) -> Iterator[dict]:
    """Yield project descriptors for public projects whose root contains isa.investigation.xlsx."""
    with httpx.Client(base_url=base_url, timeout=15.0) as client:
        for page in range(1, max_pages + 1):
            resp = client.get(
                "/api/v4/projects",
                params={"visibility": "public", "archived": "false", "per_page": 100, "page": page},
            )
            resp.raise_for_status()
            projects = resp.json()
            if not projects:
                return
            for project in projects:
                if _has_isa(client, project):
                    yield {
                        "project_id": project["id"],
                        "path_with_namespace": project["path_with_namespace"],
                        "default_branch": project.get("default_branch"),
                        "web_url": project["web_url"],
                        "last_activity_at": project.get("last_activity_at"),
                    }


def _has_isa(client: httpx.Client, project: dict) -> bool:
    branch = project.get("default_branch")
    if not branch:
        return False
    path = f"/api/v4/projects/{project['id']}/repository/files/{_ISA_PATH}/raw"
    try:
        resp = client.head(path, params={"ref": branch}, follow_redirects=True)
    except httpx.HTTPError as exc:
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
            logger.warning("isa GET probe failed for %s: %s", project["path_with_namespace"], exc)
            return False
        return resp.status_code in (200, 206)
    return False
