"""The pygeoapi role must be able to read the views and nothing else.

It is the credential a public, unauthenticated service carries, so "read-only"
has to be enforced by the database rather than by pygeoapi's good behaviour.
"""
from __future__ import annotations

import psycopg
import pytest

pytestmark = pytest.mark.db

_RO_DSN_TEMPLATE = "host=localhost port=5432 dbname=interplant user=pygeoapi_ro password={}"
_PASSWORD = "test-ro-password"


@pytest.fixture
def ro_conn(pg_dsn: str):
    from harvester import db

    with psycopg.connect(pg_dsn, autocommit=True) as admin:
        db.apply_schema(admin)
        db.apply_catalog_views(admin)
        db.apply_pygeoapi_role(admin, password=_PASSWORD)
    with psycopg.connect(_RO_DSN_TEMPLATE.format(_PASSWORD), autocommit=True) as conn:
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