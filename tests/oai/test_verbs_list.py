"""Verbs: ListIdentifiers, ListRecords, GetRecord, resumption, from/until."""
from __future__ import annotations

from datetime import UTC, datetime
from xml.etree.ElementTree import fromstring

import oai.verbs as verbs
from oai.verbs import RepoConfig, handle
from tests.oai.conftest import FakeSource

OAI = "http://www.openarchives.org/OAI/2.0/"
BASE = "https://interplant.example/oai"


def _utc(day):
    return datetime(2026, 6, day, tzinfo=UTC)


def _records(make_record, n):
    return [make_record(f"rec{i:02d}", _utc(i + 1)) for i in range(n)]


def _call(params, source):
    return fromstring(handle(params, base_url=BASE, source=source, config=RepoConfig()))


def test_get_record_returns_documentschema(make_record):
    src = FakeSource(_records(make_record, 1))
    root = _call(
        {"verb": "GetRecord", "identifier": "oai:interplant:rec00",
         "metadataPrefix": "documentschema"},
        src,
    )
    ident = root.find(f".//{{{OAI}}}header/{{{OAI}}}identifier")
    assert ident.text == "oai:interplant:rec00"
    doc = root.find(f".//{{{OAI}}}metadata/*")
    assert doc.tag.endswith("}document")


def test_get_record_unknown_id(make_record):
    root = _call(
        {"verb": "GetRecord", "identifier": "oai:interplant:ghost",
         "metadataPrefix": "oai_dc"},
        FakeSource(_records(make_record, 1)),
    )
    assert root.find(f"{{{OAI}}}error").get("code") == "idDoesNotExist"


def test_get_record_bad_prefix(make_record):
    root = _call(
        {"verb": "GetRecord", "identifier": "oai:interplant:rec00",
         "metadataPrefix": "marcxml"},
        FakeSource(_records(make_record, 1)),
    )
    assert root.find(f"{{{OAI}}}error").get("code") == "cannotDisseminateFormat"


def test_list_records_missing_prefix_is_bad_argument(make_record):
    root = _call({"verb": "ListRecords"}, FakeSource(_records(make_record, 1)))
    assert root.find(f"{{{OAI}}}error").get("code") == "badArgument"


def test_list_records_empty_match(make_record):
    root = _call(
        {"verb": "ListRecords", "metadataPrefix": "oai_dc",
         "from": "2099-01-01"},
        FakeSource(_records(make_record, 3)),
    )
    assert root.find(f"{{{OAI}}}error").get("code") == "noRecordsMatch"


def test_list_identifiers_has_headers_no_metadata(make_record):
    root = _call(
        {"verb": "ListIdentifiers", "metadataPrefix": "oai_dc"},
        FakeSource(_records(make_record, 3)),
    )
    headers = root.findall(f".//{{{OAI}}}ListIdentifiers/{{{OAI}}}header")
    assert len(headers) == 3
    assert root.find(f".//{{{OAI}}}metadata") is None


def test_resumption_token_paging(monkeypatch, make_record):
    monkeypatch.setattr(verbs, "PAGE_SIZE", 2)
    src = FakeSource(_records(make_record, 5))
    root = _call({"verb": "ListRecords", "metadataPrefix": "oai_dc"}, src)
    recs = root.findall(f".//{{{OAI}}}ListRecords/{{{OAI}}}record")
    token_el = root.find(f".//{{{OAI}}}resumptionToken")
    assert len(recs) == 2
    assert token_el is not None and token_el.text

    # follow the token to completion
    seen = len(recs)
    token = token_el.text
    while token:
        root = _call({"verb": "ListRecords", "resumptionToken": token}, src)
        recs = root.findall(f".//{{{OAI}}}ListRecords/{{{OAI}}}record")
        seen += len(recs)
        tok = root.find(f".//{{{OAI}}}resumptionToken")
        token = tok.text if tok is not None else None
    assert seen == 5


def test_resumption_token_exclusive_with_other_args(make_record):
    root = _call(
        {"verb": "ListRecords", "resumptionToken": "abc", "metadataPrefix": "oai_dc"},
        FakeSource(_records(make_record, 1)),
    )
    assert root.find(f"{{{OAI}}}error").get("code") == "badArgument"


def test_bad_resumption_token(make_record):
    root = _call(
        {"verb": "ListRecords", "resumptionToken": "!!!not-base64!!!"},
        FakeSource(_records(make_record, 1)),
    )
    assert root.find(f"{{{OAI}}}error").get("code") == "badResumptionToken"


def test_from_until_filter(make_record):
    root = _call(
        {"verb": "ListIdentifiers", "metadataPrefix": "oai_dc",
         "from": "2026-06-02", "until": "2026-06-03"},
        FakeSource(_records(make_record, 5)),
    )
    ids = [e.text for e in root.iter(f"{{{OAI}}}identifier")]
    assert ids == ["oai:interplant:rec01", "oai:interplant:rec02"]
