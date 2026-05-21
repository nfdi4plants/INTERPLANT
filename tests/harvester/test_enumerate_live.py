"""Live env-gated test for harvester.enumerate against DataPLANT GitLab."""
from __future__ import annotations

import os

import pytest

from harvester.enumerate import iter_public_arcs

pytestmark = pytest.mark.live


def test_iter_public_arcs_returns_at_least_one_arc() -> None:
    base_url = os.environ.get("INTERPLANT_GITLAB_URL", "https://git.nfdi4plants.org")
    arcs = list(iter_public_arcs(base_url, max_pages=1))
    assert len(arcs) >= 1
    first = arcs[0]
    for field in ("project_id", "path_with_namespace", "default_branch", "web_url"):
        assert field in first
        assert first[field] is not None
