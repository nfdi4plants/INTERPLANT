"""Pure (no-DB) tests for the Flask HTTP layer: protocol-arg handling."""
from __future__ import annotations

from xml.etree.ElementTree import fromstring

OAI = "http://www.openarchives.org/OAI/2.0/"


def test_duplicate_argument_is_bad_argument(monkeypatch):
    # Unreachable DSN on purpose: a duplicate must be rejected before any
    # source dispatch, so no connection is ever attempted.
    monkeypatch.setenv("INTERPLANT_DSN", "postgresql://u:p@localhost:1/none")
    from oai.app import create_app

    client = create_app().test_client()
    resp = client.get("/oai?verb=Identify&verb=ListRecords")
    root = fromstring(resp.data)
    err = root.find(f"{{{OAI}}}error")
    assert err is not None
    assert err.get("code") == "badArgument"


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
