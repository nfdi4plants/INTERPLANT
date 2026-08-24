"""Unit tests for harvester.enumerate pagination (no live network)."""
from __future__ import annotations

from unittest.mock import patch

import httpx

import harvester.enumerate as enum_mod

_PROJECT = {
    "id": 1,
    "path_with_namespace": "a/one",
    "default_branch": "main",
    "web_url": "https://g/one",
    "last_activity_at": "t1",
}


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

    monkeypatch.setattr(enum_mod, "_has_isa", lambda client, project, stats: True)
    with patch.object(enum_mod.httpx, "Client", FakeClient):
        result = list(enum_mod.iter_public_arcs("https://g", max_pages=None))

    assert [r["project_id"] for r in result] == [1, 2]


class _Resp:
    def __init__(self, status_code):
        self.status_code = status_code


def test_has_isa_counts_a_head_probe_failure_without_raising():
    class FlakyClient:
        def head(self, *a, **k):
            raise httpx.ConnectError("boom")

    stats = enum_mod.ProbeStats()
    ok = enum_mod._has_isa(FlakyClient(), _PROJECT, stats)
    assert ok is False
    assert stats.failures == 1


def test_has_isa_counts_a_get_fallback_probe_failure_without_raising():
    class FlakyClient:
        def head(self, *a, **k):
            return _Resp(404)

        def get(self, *a, **k):
            raise httpx.ConnectError("boom")

    stats = enum_mod.ProbeStats()
    ok = enum_mod._has_isa(FlakyClient(), _PROJECT, stats)
    assert ok is False
    assert stats.failures == 1


def test_has_isa_does_not_count_a_genuine_absence_as_a_failure():
    """A project with no isa file (a clean 404 on both HEAD and GET) must
    still be excluded normally, and must not be confused with a probe that
    never got an answer."""

    class CleanClient:
        def head(self, *a, **k):
            return _Resp(404)

        def get(self, *a, **k):
            return _Resp(404)

    stats = enum_mod.ProbeStats()
    ok = enum_mod._has_isa(CleanClient(), _PROJECT, stats)
    assert ok is False
    assert stats.failures == 0


def test_iter_public_arcs_reports_probe_failures_via_the_caller_owned_stats():
    """Regression for the enumeration-miss-deletes-records hazard: a caller
    must be able to tell a transient GitLab failure apart from a project
    that genuinely has no isa file, using an object it owns."""
    pages = {1: [_PROJECT, {**_PROJECT, "id": 2, "path_with_namespace": "a/two"}], 2: []}

    class FakeResp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, path, params=None, headers=None, follow_redirects=None):
            if path == "/api/v4/projects":
                return FakeResp(pages[params["page"]])
            raise AssertionError("no GET fallback expected in this test")

        def head(self, path, params=None, follow_redirects=None):
            raise httpx.ConnectError("boom")

    stats = enum_mod.ProbeStats()
    with patch.object(enum_mod.httpx, "Client", FakeClient):
        result = list(enum_mod.iter_public_arcs("https://g", max_pages=None, stats=stats))

    assert result == []
    assert stats.failures == 2
