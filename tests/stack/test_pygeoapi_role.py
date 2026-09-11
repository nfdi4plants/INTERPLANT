"""The pygeoapi role must be able to read the views and nothing else.

It is the credential a public, unauthenticated service carries, so "read-only"
has to be enforced by the database rather than by pygeoapi's good behaviour.
"""
from __future__ import annotations

import psycopg
import pytest

from tests.stack.conftest import RO_PASSWORD

pytestmark = pytest.mark.db


@pytest.fixture
def ro_conn(pg_dsn: str, ro_dsn: str):
    from harvester import db

    with psycopg.connect(pg_dsn, autocommit=True) as admin:
        db.apply_schema(admin)
        db.apply_catalog_views(admin)
        db.apply_pygeoapi_role(admin, password=RO_PASSWORD)
    with psycopg.connect(ro_dsn, autocommit=True) as conn:
        yield conn


def test_the_role_can_read_the_locations_view(ro_conn) -> None:
    with ro_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM public.arc_locations")
        assert cur.fetchone()[0] >= 0


def test_the_role_cannot_write_to_records(ro_conn) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with ro_conn.cursor() as cur:
            cur.execute("INSERT INTO public.records (id, payload) VALUES ('x', '{}'::jsonb)")


def test_the_role_cannot_read_records_directly(ro_conn) -> None:
    # It reads through the views, which is all pygeoapi needs. Granting the
    # base table would hand a public service more than the API ever exposes.
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with ro_conn.cursor() as cur:
            cur.execute("SELECT 1 FROM public.records")


def test_the_role_carries_a_statement_timeout_under_the_swap_lock_timeout(ro_conn) -> None:
    # D4: publish.swap uses lock_timeout = '5s'. The reader must die first, or
    # it aborts the nightly publish. See test_swap_survives_slow_reader.py.
    with ro_conn.cursor() as cur:
        cur.execute("SHOW statement_timeout")
        value = cur.fetchone()[0]
    assert value == "3s", f"expected 3s, got {value!r}"


def test_every_served_collection_is_readable_by_the_role(ro_conn) -> None:
    """Grants are hand-listed in sql/pygeoapi_role.sql; seven view names are
    generated from catalog/collections/*.yaml. Adding a descriptor creates a
    view and collection with no grant - a 500 in production with green CI
    unless something pins the two together."""
    from pathlib import Path

    import yaml

    config = yaml.safe_load(
        Path(__file__).parent.parent.parent.joinpath("pygeoapi-config.yml").read_text()
    )
    tables = [
        provider["table"]
        for resource in config["resources"].values()
        if isinstance(resource, dict) and resource.get("type") == "collection"
        for provider in resource["providers"]
    ]
    assert len(tables) == 9, f"expected 9 served tables, found {len(tables)}"
    for table in tables:
        with ro_conn.cursor() as cur:
            cur.execute(f"SELECT 1 FROM public.{table} LIMIT 1")  # noqa: S608 - name derived from the committed config


def test_the_role_cannot_write_through_a_view(ro_conn) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with ro_conn.cursor() as cur:
            cur.execute("INSERT INTO public.arc_records_genomics (id) VALUES ('x')")