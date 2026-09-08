"""Acquire ARCs as local directories: live (enumerate + shallow clone) or local scan.

`iter_live_arcs` / `iter_local_arcs` yield ArcIdentity. For live identities the
caller clones via `clone_arc`; for local identities `local_dir` is already set.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from harvester.enumerate import ProbeStats, iter_public_arcs
from harvester.exclusions import is_cost_excluded

logger = logging.getLogger("harvester.acquire")

_ISA = "isa.investigation.xlsx"


@dataclass
class ArcIdentity:
    path: str
    web_url: str
    project_id: int = 0
    last_activity_at: str = ""
    local_dir: str | None = None


def clone_arc(web_url: str, dest, *, timeout: int = 60, retries: int = 2) -> tuple[bool, str]:
    """Shallow-clone an ARC (LFS skipped). retries=2 means up to 3 attempts."""
    dest = Path(dest)
    clone_url = web_url.rstrip("/") + ".git"
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}
    last_err = ""
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        # git clone needs an empty target; clear partial state from a prior attempt.
        if dest.exists() and any(dest.iterdir()):
            shutil.rmtree(dest)
            dest.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", clone_url, str(dest)],
                capture_output=True, text=True, timeout=timeout, env=env,
            )
            if result.returncode == 0:
                return True, ""
            last_err = (result.stderr or result.stdout or "").strip()[:200]
        except subprocess.TimeoutExpired:
            last_err = f"clone timed out after {timeout}s"
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "clone attempt %d/%d failed for %s: %s", attempt, attempts, clone_url, last_err
        )
    return False, last_err


def iter_live_arcs(
    gitlab_base: str, *, max_pages: int | None = None, stats: ProbeStats | None = None
) -> Iterator[ArcIdentity]:
    """Yield live ARC identities, minus the cost-excluded ones.

    `stats`, if given, is incremented in place on every isa-probe failure
    during enumeration (see enumerate.ProbeStats); pass one owned by the
    caller to tell a transient GitLab failure apart from a project that
    genuinely has no isa file.

    Cost-excluded paths (harvester/exclusions.py) are dropped here rather
    than after parse. This is the only stage that skips their clone and
    parse, and the only one that keeps them out of the enumeration handed
    to publish.swap - a path left in that snapshot would land in
    diff.changed on every last_activity_at bump and trigger a full,
    pointless whole-corpus harvest. iter_local_arcs is deliberately NOT
    filtered, so `ingest` and `harvest --local-dir` remain the manual
    escape hatch.
    """
    for meta in iter_public_arcs(gitlab_base, max_pages=max_pages, stats=stats):
        path = meta["path_with_namespace"]
        if is_cost_excluded(path):
            logger.info("skipping %s: cost-excluded from live enumeration", path)
            continue
        yield ArcIdentity(
            path=path,
            web_url=meta["web_url"],
            project_id=meta["project_id"],
            last_activity_at=meta.get("last_activity_at") or "",
            local_dir=None,
        )


def iter_local_arcs(root) -> Iterator[ArcIdentity]:
    root = Path(root)
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        if (child / _ISA).exists():
            yield ArcIdentity(
                path=child.name,
                web_url=child.resolve().as_uri(),
                local_dir=str(child.resolve()),
            )
