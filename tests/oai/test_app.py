"""Pure (no-DB) tests for the Flask HTTP layer: protocol-arg handling."""
from __future__ import annotations

from xml.etree.ElementTree import fromstring

import pytest

OAI = "http://www.openarchives.org/OAI/2.0/"


def test_duplicate_verb_is_bad_verb(monkeypatch):
    # A repeated verb is badVerb per OAI-PMH 2.0, not badArgument.
    # Unreachable DSN on purpose: rejected before any source dispatch.
    monkeypatch.setenv("INTERPLANT_DSN", "postgresql://u:p@localhost:1/none")
    from oai.app import create_app

    client = create_app().test_client()
    resp = client.get("/oai?verb=Identify&verb=ListRecords")
    root = fromstring(resp.data)
    err = root.find(f"{{{OAI}}}error")
    assert err is not None
    assert err.get("code") == "badVerb"


def test_duplicate_metadata_prefix_is_bad_argument(monkeypatch):
    monkeypatch.setenv("INTERPLANT_DSN", "postgresql://u:p@localhost:1/none")
    from oai.app import create_app

    client = create_app().test_client()
    resp = client.get(
        "/oai?verb=ListRecords&metadataPrefix=oai_dc&metadataPrefix=documentschema"
    )
    root = fromstring(resp.data)
    err = root.find(f"{{{OAI}}}error")
    assert err is not None
    assert err.get("code") == "badArgument"


def test_base_url_override_is_advertised(monkeypatch):
    monkeypatch.setenv("INTERPLANT_DSN", "postgresql://u:p@localhost:1/none")
    monkeypatch.setenv("INTERPLANT_OAI_BASE_URL", "https://www.plabipd.de/oai")
    # Identify's earliestDatestamp field reaches the source, unlike badVerb/
    # badArgument above; stub it so this pure (no-DB) test never dials out.
    monkeypatch.setattr("oai.source.RecordSource.earliest_datestamp", lambda self: None)
    from oai.app import create_app

    client = create_app().test_client()
    body = client.get("/oai", query_string={"verb": "Identify"}).data.decode()
    assert "<baseURL>https://www.plabipd.de/oai</baseURL>" in body


def test_base_url_falls_back_to_request_when_unset(monkeypatch):
    monkeypatch.setenv("INTERPLANT_DSN", "postgresql://u:p@localhost:1/none")
    monkeypatch.delenv("INTERPLANT_OAI_BASE_URL", raising=False)
    monkeypatch.setattr("oai.source.RecordSource.earliest_datestamp", lambda self: None)
    from oai.app import create_app

    client = create_app().test_client()
    body = client.get("/oai", query_string={"verb": "Identify"}).data.decode()
    assert "<baseURL>http://localhost/oai</baseURL>" in body


def test_missing_dsn_is_fatal(monkeypatch):
    monkeypatch.delenv("INTERPLANT_DSN", raising=False)
    from oai.app import create_app

    with pytest.raises(RuntimeError, match="INTERPLANT_DSN"):
        create_app()
