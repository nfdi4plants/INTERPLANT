"""Unit tests for harvester.enumerate pagination (no live network)."""
from __future__ import annotations

from unittest.mock import patch

import harvester.enumerate as enum_mod


def test_iter_public_arcs_paginates_until_empty(monkeypatch):
    pages = {
        1: [{"id": 1, "path_with_namespace": "a/one", "default_branch": "main",
             "web_url": "https://g/one", "last_activity_at": "t1"}],
        2: [{"id": 2, "path_with_namespace": "a/two", "default_branch": "main",
             "web_url": "https://g/two", "last_activity_at": "t2"}],
        3: [],
    }

    class FakeResp:
        def __init__(self, data): self._data = data
        def raise_for_status(self): pass
        def json(self): return self._data

    class FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, path, params=None):
            return FakeResp(pages[params["page"]])

    monkeypatch.setattr(enum_mod, "_has_isa", lambda client, project: True)
    with patch.object(enum_mod.httpx, "Client", FakeClient):
        result = list(enum_mod.iter_public_arcs("https://g", max_pages=None))

    assert [r["project_id"] for r in result] == [1, 2]
