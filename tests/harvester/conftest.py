"""Gating for harvester tests.

- Tests marked `db` are skipped unless INTERPLANT_STACK_TESTS=1 (mirrors tests/stack/).
- Tests marked `live` are skipped unless INTERPLANT_LIVE_HARVEST=1.
"""
from __future__ import annotations

import os

import pytest

_STACK_GATE = "INTERPLANT_STACK_TESTS"
_LIVE_GATE = "INTERPLANT_LIVE_HARVEST"
_DEFAULT_DSN = "postgresql://interplant:interplant@localhost:5432/interplant"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    stack_enabled = os.environ.get(_STACK_GATE) == "1"
    live_enabled = os.environ.get(_LIVE_GATE) == "1"
    skip_db = pytest.mark.skip(reason=f"set {_STACK_GATE}=1 to enable db-backed tests")
    skip_live = pytest.mark.skip(reason=f"set {_LIVE_GATE}=1 to enable live-network tests")
    for item in items:
        if "db" in item.keywords and not stack_enabled:
            item.add_marker(skip_db)
        if "live" in item.keywords and not live_enabled:
            item.add_marker(skip_live)


@pytest.fixture
def pg_dsn() -> str:
    return os.environ.get("INTERPLANT_PG_DSN", _DEFAULT_DSN)
