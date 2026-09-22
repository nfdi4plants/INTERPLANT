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
from psycopg.conninfo import make_conninfo

from harvester import db

DEFAULT_PG_DSN = "postgresql://interplant:interplant@localhost:5432/interplant"
DEFAULT_PYGEOAPI_URL = "http://localhost:5000"

# Shared by test_pygeoapi_role.py and test_swap_survives_slow_reader.py, which
# both provision the pygeoapi_ro role with this password before connecting as it.
RO_PASSWORD = "test-ro-password"

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
        # Dev is served as pygeoapi_ro, so a fixture that rebuilt the views must
        # restore their ACLs (another test's DROP ... CASCADE may have taken
        # them). Mirrors the contract install.sh guarantees on production.
        db.create_pygeoapi_role(conn, password=RO_PASSWORD)
        db.apply_pygeoapi_role(conn)
        yield conn


# Raw payloads as the harvester stores them in public.records: the view
# (sql/catalog_views.sql) reads `affiliation`, `orcid` and `uniqueId` and
# renames them to organization, identifier and externalIds on the way out.
_PAGE_RECORDS = {
    "point": {
        "id": "zz-stacktest-point",
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [6.7926, 51.1889]},
        "properties": {
            "title": "Stack test: single point",
            "description": "Seeded by tests/stack/conftest.py.",
            "created": "2026-09-22T00:00:00+00:00",
            "omics_domains": ["proteomics"],
            "experiment_context": "lab",
            "organism": ["Arabidopsis thaliana"],
            "keywords": [],
            "arc_source_uri": "https://git.nfdi4plants.org/example/stacktest-point",
            "uniqueId": "11111111-2222-5333-8444-555555555555",
            "contacts": [
                {"name": "Ada Lovelace", "affiliation": "FZJ",
                 "orcid": "0000-0002-1825-0097"}
            ],
        },
    },
    "multipoint": {
        "id": "zz-stacktest-multipoint",
        "type": "Feature",
        "geometry": {
            "type": "MultiPoint",
            "coordinates": [[11.27888, 51.826197], [101.13511, 12.73322]],
        },
        "properties": {
            "title": "Stack test: multipoint",
            "description": "Seeded by tests/stack/conftest.py.",
            "created": "2026-09-22T00:00:00+00:00",
            "omics_domains": ["genomics"],
            "experiment_context": "lab",
            "organism": [],
            "keywords": [],
            "arc_source_uri": "https://git.nfdi4plants.org/example/stacktest-multipoint",
            "uniqueId": "66666666-7777-5888-9999-000000000000",
            "contacts": [],
        },
    },
}


@pytest.fixture
def seeded_record_pages(pg_dsn: str):
    """Seed one Point and one MultiPoint record, and remove them afterwards.

    Unlike seeded_locations this cleans up, because these rows appear on the
    public items list of whatever dev stack runs the suite."""
    ids = [record["id"] for record in _PAGE_RECORDS.values()]
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            for record in _PAGE_RECORDS.values():
                cur.execute(
                    "INSERT INTO public.records (id, payload) VALUES (%s, %s) "
                    "ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload",
                    (record["id"], json.dumps(record)),
                )
        try:
            yield {kind: record["id"] for kind, record in _PAGE_RECORDS.items()}
        finally:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM public.records WHERE id = ANY(%s)", (ids,))


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
def ro_dsn(pg_dsn: str) -> str:
    """The pygeoapi_ro role's DSN, derived from pg_dsn rather than hardcoded.

    pg_dsn already points at the right host (localhost in dev, `db` in CI, a
    docker-network address wherever else), so swapping in the ro role's user
    and password keeps this test suite pointed at the same Postgres instead
    of a hardcoded localhost that CI's Postgres never listens on.
    """
    return make_conninfo(pg_dsn, user="pygeoapi_ro", password=RO_PASSWORD)


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
