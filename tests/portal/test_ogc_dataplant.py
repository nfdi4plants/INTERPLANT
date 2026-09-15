"""The DataPLANT subclass differs from the generic reader in one way: its
uniqueId is the ARC uuid5, so an OGC document and an OAI document for the same
ARC are one document in the portal index."""
from __future__ import annotations

import json

from oai.mapping import map_record
from tests.portal.stub_ogc_server import StubOGC

UUID = "0bf1e5a0-0000-5000-8000-000000000001"


def _item(external_ids):
    return {"type": "Feature", "id": "dataplant-x", "geometry": None,
            "properties": {"title": "T", "created": "2026-06-24T00:00:00Z",
                           "externalIds": external_ids}}


def _harvester(module, tmp_path, record):
    h = module.DataPlantArcOGCHarvester(url="https://example.org/ogc",
                                        collections=module.COLLECTIONS,
                                        logfile=str(tmp_path / "h.log"))
    h.current_collection = "arc-records"
    h.current_record = record
    return h


def test_unique_id_is_the_urn_uuid_external_id(ogc_dataplant_module, tmp_path):
    h = _harvester(ogc_dataplant_module, tmp_path,
                   _item([{"scheme": "other", "value": "nope"},
                          {"scheme": "urn:uuid", "value": UUID}]))
    assert h.get_unique_id() == UUID


def test_resources_still_link_to_the_item_url(ogc_dataplant_module, tmp_path):
    h = _harvester(ogc_dataplant_module, tmp_path, _item([{"scheme": "urn:uuid", "value": UUID}]))
    assert h.get_resources("T")[0]["uri"].endswith("/collections/arc-records/items/dataplant-x")


def test_no_urn_uuid_means_the_record_is_dropped_not_url_keyed(ogc_dataplant_module, tmp_path):
    """Falling back to the URL would give the ARC a second identity next to its
    OAI document. Dropping it, with their standard warning, is the safe failure."""
    h = _harvester(ogc_dataplant_module, tmp_path, _item([]))
    assert h.get_unique_id() is None
    assert h.prepare_record() is None


def test_ogc_and_oai_documents_share_a_unique_id(ogc_dataplant_module, load_json, tmp_path, capsys):
    """End to end on the canonical fixture, with the feature built by hand from
    it: the subclass reads the urn:uuid externalId and the harvested uniqueId
    equals the OAI mapper's uniqueId for the same record. The view side (that
    arc-records actually emits this externalId) is covered separately by
    tests/stack/test_arc_records_records_core.py."""
    record = load_json("examples/record-complete.json")
    oai_unique_id = map_record(record)["uniqueId"]
    feature = {"type": "Feature", "id": record["id"], "geometry": record.get("geometry"),
               "properties": {"title": record["properties"]["title"],
                              "created": record["properties"]["created"],
                              "externalIds": [{"scheme": "urn:uuid",
                                               "value": record["properties"]["uniqueId"]}]}}

    with StubOGC(features=[feature], mode="next") as stub:
        h = ogc_dataplant_module.DataPlantArcOGCHarvester(
            url=stub.base, collections=["c"], logfile=str(tmp_path / "h.log"))
        h.harvest({}, exit_on_exception=False)

    out = capsys.readouterr().out
    documents = [json.loads(line) for line in out.splitlines() if line.strip().startswith("{")]
    assert [d["uniqueId"] for d in documents] == [oai_unique_id]