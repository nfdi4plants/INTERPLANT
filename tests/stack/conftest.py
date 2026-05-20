"""Shared fixtures and gating for live-stack smoke tests.

These tests require a running `compose.yaml` stack (or, in CI, the equivalent
GitLab CI services). They are skipped unless INTERPLANT_STACK_TESTS=1.
"""
from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest

DEFAULT_PG_DSN = "postgresql://interplant:interplant@localhost:5432/interplant"
DEFAULT_PYGEOAPI_URL = "http://localhost:5000"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip every stack test unless the env gate is set."""
    if os.environ.get("INTERPLANT_STACK_TESTS") == "1":
        return
    skip_marker = pytest.mark.skip(
        reason="set INTERPLANT_STACK_TESTS=1 to enable stack smoke tests"
    )
    for item in items:
        item.add_marker(skip_marker)


@pytest.fixture
def pg_dsn() -> str:
    return os.environ.get("INTERPLANT_PG_DSN", DEFAULT_PG_DSN)


@pytest.fixture
def pygeoapi_url() -> str:
    return os.environ.get("INTERPLANT_PYGEOAPI_URL", DEFAULT_PYGEOAPI_URL)


def _tcp_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture
def pygeoapi_reachable(pygeoapi_url: str) -> bool:
    parsed = urlparse(pygeoapi_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return _tcp_reachable(host, port)
