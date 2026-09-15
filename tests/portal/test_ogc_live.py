"""Harvest the public OGC endpoint end to end and prove the fallback is safe:
every document's uniqueId is a uniqueId the public OAI endpoint also emits.

Double-gated on top of the tests/portal/conftest.py gate
(INTERPLANT_PORTAL_TESTS=1 + a local o2a clone): this file also requires
INTERPLANT_LIVE_TESTS=1, because it reads someone else's production server
over the network. Without both, pytest_collection_modifyitems in conftest
already marks every item in this directory skip, and the module-level
skipif below is a second, independent gate, so a normal run never even
constructs the fixtures that would open a socket.
"""
from __future__ import annotations

import json
import os
import urllib.request
import xml.etree.ElementTree as ET

import pytest

OGC = os.environ.get("INTERPLANT_OGC_URL", "https://www.plabipd.de/ogc")
OAI = os.environ.get("INTERPLANT_OAI_URL", "https://www.plabipd.de/oai")
OAI_NS = {"o": "http://www.openarchives.org/OAI/2.0/"}

pytestmark = pytest.mark.skipif(
    os.environ.get("INTERPLANT_LIVE_TESTS") != "1",
    reason="set INTERPLANT_LIVE_TESTS=1 to read the public endpoints",
)

# Observed on the live corpus 2026-09-15 (153 records): 125 carry contacts,
# 93 carry an ORCID. Used only as sanity floors, never as equality checks -
# the corpus grows, so a shrinking count would be a real regression but an
# exact count is not the thing being tested here.
_MIN_ORCID_DOCUMENTS = 1


def _oai_unique_ids() -> set[str]:
    """Page the public OAI-PMH endpoint with resumptionToken and collect
    every uniqueId it emits, exactly as the plan's Task 4 registration
    fragment says the AWI harvester would."""
    ids = set()
    url = f"{OAI}?verb=ListRecords&metadataPrefix=documentschema"
    while url:
        root = ET.XML(urllib.request.urlopen(url, timeout=60).read())
        for metadata in root.findall(".//o:record/o:metadata", OAI_NS):
            ids.add(json.loads(list(metadata)[0].text)["uniqueId"])
        token = root.find(".//o:resumptionToken", OAI_NS)
        url = (
            f"{OAI}?verb=ListRecords&resumptionToken={token.text}"
            if token is not None and token.text
            else None
        )
    return ids


def _harvest_ogc(ogc_dataplant_module, tmp_path, capsys) -> list[dict]:
    h = ogc_dataplant_module.DataPlantArcOGCHarvester(
        url=OGC, collections=ogc_dataplant_module.COLLECTIONS, page_size=50,
        logfile=str(tmp_path / "h.log"),
    )
    h.harvest({}, exit_on_exception=False)
    out = capsys.readouterr().out
    return [json.loads(line) for line in out.splitlines() if line.strip().startswith("{")]


def test_live_harvest_is_complete_valid_and_shares_identity_with_oai(
    ogc_dataplant_module, tmp_path, capsys
):
    from helper.Validator import Validator

    documents = _harvest_ogc(ogc_dataplant_module, tmp_path, capsys)

    matched = json.loads(urllib.request.urlopen(
        f"{OGC}/collections/arc-records/items?limit=1&f=json", timeout=60,
    ).read())["numberMatched"]

    # 1. Completeness.
    assert len(documents) == matched, "every published record must become a document"
    ogc_ids = [d["uniqueId"] for d in documents]
    assert len(set(ogc_ids)) == len(ogc_ids), "uniqueIds must be unique"

    # 2. Validity: every harvested document passes the strict vendored Validator.
    validator = Validator()
    for document in documents:
        result = validator.validate(document, return_validation=True)
        assert result is True, f"record {document.get('id')} failed validation: {result}"

    # 3. Shared identity between the OGC and OAI paths. A nightly publish can
    # land between the OGC read above and the OAI read below and make the two
    # sets differ spuriously (a record added, removed or re-keyed in that
    # window). Re-read the OAI side once and compare again before failing; a
    # mismatch that survives a second read is a real defect, not a race, so
    # this does not retry a third time and does not filter anything out.
    ogc_id_set = set(ogc_ids)
    oai_id_set = _oai_unique_ids()
    if ogc_id_set != oai_id_set:
        oai_id_set = _oai_unique_ids()
    assert ogc_id_set == oai_id_set, "OGC and OAI must give every ARC one identity"

    # 4. Attribution survived the round trip: at least one document carries a
    # real ORCID through Task 1's view and Task 3's get_persons mapping.
    orcid_documents = [
        d for d in documents
        if any(
            person.get("identifiers", {}).get("orcid")
            for people in d.get("persons", {}).values()
            for person in people
        )
    ]
    assert len(orcid_documents) >= _MIN_ORCID_DOCUMENTS, (
        f"expected at least one harvested document with an ORCID, got {len(orcid_documents)}"
    )
