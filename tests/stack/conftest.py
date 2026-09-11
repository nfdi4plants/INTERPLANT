"""Shared fixtures and gating for live-stack smoke tests.

These tests require a running `compose.yaml` stack (or, in CI, the equivalent
GitLab CI services). They are skipped unless INTERPLANT_STACK_TESTS=1.
"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

import psycopg
import pytest

from harvester import db

DEFAULT_PG_DSN = "postgresql://interplant:interplant@localhost:5432/interplant"
DEFAULT_PYGEOAPI_URL = "http://localhost:5000"

_STACK_DIR = Path(__file__).parent

_MULTI = {
    "id": "dataplant-multi",
    "type": "Feature",
    "geometry": {
        "type": "MultiPoint",
        "coordinates": [[-99.791667, 18.485833], [-99.8025, 18.4675]],
    },
    "properties": {
        "location_status": "extracted",
        "locations": [
            {"role": "collection-site", "label": "ACC-1", "label_field": "ACCESION",
             "point": [-99.791667, 18.485833], "precision": "exact", "n_rows": 13,
             "source": "studies/initial_data/isa.study.xlsx#t"},
            {"role": "collection-site", "label": "ACC-2", "label_field": "ACCESION",
             "point": [-99.8025, 18.4675], "precision": "exact", "n_rows": 7,
             "source": "studies/initial_data/isa.study.xlsx#t"},
            {"role": "custodian-institution", "label": "HHU",
             "label_field": "Investigation Person Affiliation",
             "point": [6.7926, 51.1889], "precision": "institution", "n_rows": 1,
             "source": "affiliation"},
        ],
    },
}
_EMPTY = {
    "id": "dataplant-empty",
    "type": "Feature",
    "geometry": None,
    "properties": {"location_status": "absent", "locations": []},
}


@pytest.fixture
def seeded_locations(pg_dsn: str):
    """Seed one record with three points across two tiers, and one with none."""
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        db.apply_schema(conn)
        with conn.cursor() as cur:
            for record in (_MULTI, _EMPTY):
                cur.execute(
                    "INSERT INTO public.records (id, payload) VALUES (%s, %s) "
                    "ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload",
                    (record["id"], json.dumps(record)),
                )
        db.apply_catalog_views(conn)
        yield conn


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip the stack tests (those under tests/stack/) unless the env gate is set.

    pytest passes the whole session's collected items to every conftest hook, so
    this must scope to its own directory; an unscoped loop would skip pure tests
    collected from other directories (e.g. tests/oai, tests/specs).
    """
    if os.environ.get("INTERPLANT_STACK_TESTS") == "1":
        return
    skip_marker = pytest.mark.skip(
        reason="set INTERPLANT_STACK_TESTS=1 to enable stack smoke tests"
    )
    for item in items:
        if item.path.is_relative_to(_STACK_DIR):
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
