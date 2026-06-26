"""Verbs: envelope, errors, Identify, ListMetadataFormats, ListSets."""
from __future__ import annotations

from xml.etree.ElementTree import fromstring

from oai.verbs import RepoConfig, handle

OAI = "http://www.openarchives.org/OAI/2.0/"
BASE = "https://interplant.example/oai"


def _call(params, source):
    return fromstring(handle(params, base_url=BASE, source=source, config=RepoConfig()))


def test_identify_reports_repository_metadata(make_record):
    src_records = [make_record("a", __import__("datetime").datetime(
        2026, 6, 24, tzinfo=__import__("datetime").timezone.utc))]
    from tests.oai.conftest import FakeSource
    root = _call({"verb": "Identify"}, FakeSource(src_records))
    ident = root.find(f"{{{OAI}}}Identify")
    assert ident.findtext(f"{{{OAI}}}repositoryName") == "INTERPLANT"
    assert ident.findtext(f"{{{OAI}}}protocolVersion") == "2.0"
    assert ident.findtext(f"{{{OAI}}}deletedRecord") == "no"
    assert ident.findtext(f"{{{OAI}}}granularity") == "YYYY-MM-DDThh:mm:ssZ"
    assert ident.findtext(f"{{{OAI}}}earliestDatestamp") == "2026-06-24T00:00:00Z"


def test_identify_empty_repo_uses_default_earliest():
    from tests.oai.conftest import FakeSource
    root = _call({"verb": "Identify"}, FakeSource([]))
    ident = root.find(f"{{{OAI}}}Identify")
    assert ident.findtext(f"{{{OAI}}}earliestDatestamp") == "2020-01-01T00:00:00Z"


def test_bad_verb_returns_error_and_omits_attrs():
    from tests.oai.conftest import FakeSource
    root = _call({"verb": "Frobnicate"}, FakeSource([]))
    err = root.find(f"{{{OAI}}}error")
    assert err.get("code") == "badVerb"
    # request element must NOT echo the bad verb attribute
    req = root.find(f"{{{OAI}}}request")
    assert req.get("verb") is None


def test_missing_verb_is_bad_verb():
    from tests.oai.conftest import FakeSource
    root = _call({}, FakeSource([]))
    assert root.find(f"{{{OAI}}}error").get("code") == "badVerb"


def test_list_metadata_formats_lists_both():
    from tests.oai.conftest import FakeSource
    root = _call({"verb": "ListMetadataFormats"}, FakeSource([]))
    prefixes = [
        e.text for e in root.iter(f"{{{OAI}}}metadataPrefix")
    ]
    assert set(prefixes) == {"oai_dc", "documentschema"}


def test_list_sets_returns_no_set_hierarchy():
    from tests.oai.conftest import FakeSource
    root = _call({"verb": "ListSets"}, FakeSource([]))
    assert root.find(f"{{{OAI}}}error").get("code") == "noSetHierarchy"
