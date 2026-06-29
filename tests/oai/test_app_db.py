"""End-to-end: the Flask app serves real records from Postgres over /oai."""
from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import fromstring

import psycopg
import pytest

from harvester import batch, db
from harvester.acquire import iter_local_arcs

OAI = "http://www.openarchives.org/OAI/2.0/"
FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures" / "arcs"


@pytest.fixture
def client(pg_dsn, monkeypatch):
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS records CASCADE")
        db.apply_schema(conn)
        batch.run_batch(
            list(iter_local_arcs(FIXTURES_ROOT)),
            conn=conn, now_iso="2026-06-24T00:00:00Z",
            run_timestamp="20260624T000000Z", source="local",
        )
    monkeypatch.setenv("INTERPLANT_DSN", pg_dsn)
    from oai.app import create_app
    app = create_app()
    app.config.update(TESTING=True)
    yield app.test_client()
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS records CASCADE")


@pytest.mark.db
def test_identify_over_http(client):
    resp = client.get("/oai?verb=Identify")
    assert resp.status_code == 200
    assert resp.mimetype == "text/xml"
    root = fromstring(resp.data)
    assert root.find(f".//{{{OAI}}}repositoryName").text == "INTERPLANT"


@pytest.mark.db
def test_listrecords_documentschema_over_http(client):
    resp = client.get("/oai?verb=ListRecords&metadataPrefix=documentschema")
    assert resp.status_code == 200
    root = fromstring(resp.data)
    records = root.findall(f".//{{{OAI}}}record")
    assert len(records) >= 3


@pytest.mark.db
def test_getrecord_over_http(client):
    resp = client.get(
        "/oai?verb=GetRecord&identifier=oai:interplant:dataplant-arcproteomics"
        "&metadataPrefix=oai_dc"
    )
    root = fromstring(resp.data)
    assert root.find(f".//{{{OAI}}}identifier").text == (
        "oai:interplant:dataplant-arcproteomics"
    )
