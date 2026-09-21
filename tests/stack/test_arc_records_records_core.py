"""Records-core contacts and externalIds on public.arc_records.

These two columns are what let the OGC path carry authors and ORCIDs, and let
an OGC-harvested document share its uniqueId with the OAI document for the
same ARC, so a fallback between the two paths updates instead of duplicating.
Requires a running Postgres (INTERPLANT_STACK_TESTS=1).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import psycopg
import pytest
import requests

from harvester import db
from oai.mapping import map_record
from tests.stack.conftest import RO_PASSWORD

pytestmark = pytest.mark.db

_COMPLETE = json.loads(
    (Path(__file__).resolve().parents[2] / "docs/specs/examples/record-complete.json")
    .read_text(encoding="utf-8")
)


def _variant(record_id: str, contacts: list) -> dict:
    record = copy.deepcopy(_COMPLETE)
    record["id"] = record_id
    record["properties"]["contacts"] = contacts
    return record


_WITH_ORCID = _variant("test-rc-orcid", [
    {"name": "Ada Lovelace", "role": "pointOfContact", "orcid": "0000-0002-1825-0097",
     "affiliation": "Analytical Engines Ltd"},
])
_AFFILIATION_ONLY = _variant("test-rc-affil", [
    {"name": "Grace Hopper", "affiliation": "Navy"},
])
_NO_CONTACTS = _variant("test-rc-none", [])
_SEEDED = (_WITH_ORCID, _AFFILIATION_ONLY, _NO_CONTACTS)


@pytest.fixture
def seeded_records_core(pg_dsn: str):
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        db.apply_schema(conn)
        with conn.cursor() as cur:
            for record in _SEEDED:
                cur.execute(
                    "INSERT INTO public.records (id, payload) VALUES (%s, %s) "
                    "ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload",
                    (record["id"], json.dumps(record)),
                )
        db.apply_catalog_views(conn)
        db.create_pygeoapi_role(conn, password=RO_PASSWORD)
        db.apply_pygeoapi_role(conn)
        try:
            yield conn
        finally:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM public.records WHERE id = ANY(%s)",
                    ([r["id"] for r in _SEEDED],),
                )


def _one(conn, sql: str, params: tuple):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


def test_contact_with_orcid_and_affiliation(seeded_records_core):
    contacts = _one(seeded_records_core,
                    "SELECT contacts FROM public.arc_records WHERE id = %s", ("test-rc-orcid",))
    assert contacts == [{
        "name": "Ada Lovelace",
        "organization": "Analytical Engines Ltd",
        "identifier": "https://orcid.org/0000-0002-1825-0097",
        "roles": ["pointOfContact"],
    }]


def test_contact_without_orcid_or_role_omits_identifier_and_defaults_role(seeded_records_core):
    """A contact with no role defaults to author, which is the only role the
    portal renders. See the comment on the contacts column in catalog_views.sql."""
    contacts = _one(seeded_records_core,
                    "SELECT contacts FROM public.arc_records WHERE id = %s", ("test-rc-affil",))
    assert contacts == [{"name": "Grace Hopper", "organization": "Navy",
                         "roles": ["author"]}]


def test_no_contacts_is_an_empty_array_not_null(seeded_records_core):
    contacts = _one(seeded_records_core,
                    "SELECT contacts FROM public.arc_records WHERE id = %s", ("test-rc-none",))
    assert contacts == []


def test_external_id_is_the_same_uniqueId_the_oai_path_emits(seeded_records_core):
    """The test that makes an OAI fallback safe: both paths, one identity."""
    external = _one(seeded_records_core,
                    'SELECT "externalIds" FROM public.arc_records WHERE id = %s',
                    ("test-rc-orcid",))
    assert external == [{"scheme": "urn:uuid", "value": map_record(_WITH_ORCID)["uniqueId"]}]


def test_domain_views_inherit_the_new_columns(seeded_records_core):
    with seeded_records_core.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'externalIds' "
            "AND table_name LIKE 'arc_records%%'"
        )
        tables = {row[0] for row in cur.fetchall()}
    assert "arc_records" in tables
    assert len(tables) == 8, f"arc_records plus the seven dataplant-* views, got {tables}"


def test_pygeoapi_serves_both_properties(seeded_records_core, pygeoapi_url, pygeoapi_reachable):
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    item = requests.get(
        f"{pygeoapi_url}/collections/arc-records/items/test-rc-orcid",
        params={"f": "json"}, timeout=30,
    ).json()
    assert item["properties"]["contacts"][0]["identifier"].startswith("https://orcid.org/")
    assert item["properties"]["externalIds"][0]["scheme"] == "urn:uuid"