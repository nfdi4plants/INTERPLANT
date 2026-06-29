"""Validate OAI envelopes against the pinned OAI-PMH XSD, and embedded payloads
against oai_dc.xsd / the portal JSON schema.

Strict XSD validation of the OAI-PMH envelope cannot descend into the foreign
`documentschema` namespace (xs:any processContents="strict"), so:
  - envelope + oai_dc responses are validated against OAI-PMH.xsd (+ oai_dc via resolver),
  - documentschema payloads are validated as JSON against the portal schema.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from xml.etree.ElementTree import fromstring

import pytest
from lxml import etree

from oai.verbs import RepoConfig, handle
from tests.oai.conftest import FakeSource

OAI = "http://www.openarchives.org/OAI/2.0/"
BASE = "https://interplant.example/oai"
SCHEMA_DIR = Path(__file__).parent / "schemas"


class _LocalResolver(etree.Resolver):
    """Resolve remote schemaLocation imports to the pinned local copies."""
    _MAP = {
        "oai_dc.xsd": "oai_dc.xsd",
        "simpledc20021212.xsd": "simpledc.xsd",
        "xml.xsd": "xml.xsd",
    }

    def resolve(self, url, public_id, context):
        for needle, local in self._MAP.items():
            if url.endswith(needle):
                return self.resolve_filename(str(SCHEMA_DIR / local), context)
        return None


@pytest.fixture(scope="module")
def oai_schema():
    parser = etree.XMLParser(load_dtd=False, no_network=True)
    parser.resolvers.add(_LocalResolver())
    doc = etree.parse(str(SCHEMA_DIR / "oai_with_dc.xsd"), parser)
    return etree.XMLSchema(doc)


def _records(make_record, n):
    return [
        make_record(f"rec{i:02d}", datetime(2026, 6, i + 1, tzinfo=UTC))
        for i in range(n)
    ]


def _validate(oai_schema, xml_bytes):
    doc = etree.fromstring(xml_bytes)
    oai_schema.assertValid(doc)


@pytest.mark.parametrize("verb", ["Identify", "ListMetadataFormats", "ListSets"])
def test_envelope_verbs_are_schema_valid(oai_schema, verb, make_record):
    xml = handle({"verb": verb}, base_url=BASE, source=FakeSource(_records(make_record, 2)),
                 config=RepoConfig())
    _validate(oai_schema, xml)


def test_oai_dc_listrecords_is_schema_valid(oai_schema, make_record):
    xml = handle({"verb": "ListRecords", "metadataPrefix": "oai_dc"},
                 base_url=BASE, source=FakeSource(_records(make_record, 3)),
                 config=RepoConfig())
    _validate(oai_schema, xml)


def test_error_response_is_schema_valid(oai_schema, make_record):
    xml = handle({"verb": "Frobnicate"}, base_url=BASE,
                 source=FakeSource(_records(make_record, 1)), config=RepoConfig())
    _validate(oai_schema, xml)


def test_documentschema_payload_is_portal_valid(make_record, schema_portal, validate_against):
    xml = handle({"verb": "ListRecords", "metadataPrefix": "documentschema"},
                 base_url=BASE, source=FakeSource(_records(make_record, 2)),
                 config=RepoConfig())
    root = fromstring(xml)
    docs = root.findall(f".//{{{OAI}}}metadata/*")
    assert docs, "expected documentschema payloads"
    for doc_el in docs:
        validate_against(schema_portal, json.loads(doc_el.text))
