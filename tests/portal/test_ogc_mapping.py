"""An OGC API Records item must become a valid portal index document."""
from __future__ import annotations

import json

from tests.portal.stub_ogc_server import StubOGC

ITEM = {
    "type": "Feature",
    "id": "dataplant-example",
    "geometry": {"type": "Point", "coordinates": [6.36, 50.9]},
    "properties": {
        "title": "An example ARC",
        "description": "desc",
        "created": "2026-06-24T00:00:00Z",
        "keywords": ["drought", "heat"],
        "contacts": [
            {"name": "Ada Lovelace", "organization": "Engines Ltd",
             "identifier": "https://orcid.org/0000-0002-1825-0097",
             "roles": ["pointOfContact"]},
            {"name": "Grace Hopper", "roles": ["pointOfContact", "author"]},
            {"organization": "Nameless Org", "roles": ["pointOfContact"]},
        ],
    },
}


def _harvester(module, tmp_path, record=ITEM):
    h = module.OGCAPIRecordsHarvester(url="https://example.org/ogc", collections=["arc-records"],
                                      logfile=str(tmp_path / "h.log"))
    h.current_collection = "arc-records"
    h.current_record = record
    return h


def test_scalar_accessors(ogc_helper_module, tmp_path):
    h = _harvester(ogc_helper_module, tmp_path)
    assert h.get_id() == "dataplant-example"
    assert h.get_title() == "An example ARC"
    assert h.get_description() == "desc"
    assert h.get_date().startswith("2026-06-24")
    assert h.get_generic_type() == "data"


def test_generic_unique_id_is_the_item_url(ogc_helper_module, tmp_path):
    h = _harvester(ogc_helper_module, tmp_path)
    assert h.get_unique_id() == "https://example.org/ogc/collections/arc-records/items/dataplant-example"


def test_title_falls_back_to_id(ogc_helper_module, tmp_path):
    h = _harvester(ogc_helper_module, tmp_path,
                   {"type": "Feature", "id": "bare", "properties": {}, "geometry": None})
    assert h.get_title() == "bare"


def test_geometry_is_passed_through_not_flattened(ogc_helper_module, tmp_path):
    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
    h = _harvester(ogc_helper_module, tmp_path, dict(ITEM, geometry=polygon))
    assert h.get_geometry() == polygon


def test_keywords_accepts_a_comma_string(ogc_helper_module, tmp_path):
    record = dict(ITEM, properties=dict(ITEM["properties"], keywords="a, b"))
    h = _harvester(ogc_helper_module, tmp_path, record)
    assert [k["name"] for k in h.get_keywords()["keyword"]] == ["a", "b"]


def test_persons_come_from_records_core_contacts(ogc_helper_module, tmp_path):
    persons = _harvester(ogc_helper_module, tmp_path).get_persons()

    ada = persons["pointOfContact"][0]
    assert ada == {"fullname": "Ada Lovelace", "organisation": "Engines Ltd",
                   "identifiers": {"orcid": "0000-0002-1825-0097"}, "role": "pointOfContact"}

    grace_roles = sorted(r for r, people in persons.items()
                         if any(p["fullname"] == "Grace Hopper" for p in people))
    assert grace_roles == ["author", "pointOfContact"], "one entry per role"
    assert persons["pointOfContact"][1]["identifiers"] == {}


def test_a_contact_without_a_name_is_skipped(ogc_helper_module, tmp_path):
    persons = _harvester(ogc_helper_module, tmp_path).get_persons()
    names = [p["fullname"] for people in persons.values() for p in people]
    assert "Nameless Org" not in names
    assert len(names) == 3


def test_resources_point_at_the_item(ogc_helper_module, tmp_path):
    h = _harvester(ogc_helper_module, tmp_path)
    assert h.get_resources(h.get_title()) == [
        {"title": "An example ARC", "uri": h.get_unique_id(), "type": "link"}]


def test_a_record_with_no_id_is_skipped_not_crashed(ogc_helper_module, tmp_path):
    h = _harvester(ogc_helper_module, tmp_path,
                   {"type": "Feature", "properties": {"title": "T"}, "geometry": None})
    assert h.prepare_record() is None


def test_harvested_documents_pass_the_portal_validator(ogc_helper_module, tmp_path, capsys):
    from helper.Validator import Validator

    features = [dict(ITEM, id=f"rec{i}") for i in range(3)]
    with StubOGC(features=features, page_size=2, mode="next") as stub:
        h = ogc_helper_module.OGCAPIRecordsHarvester(
            url=stub.base, collections=["c"], page_size=2, logfile=str(tmp_path / "h.log"))
        h.harvest({}, exit_on_exception=False)

    out = capsys.readouterr().out
    documents = [json.loads(line) for line in out.splitlines() if line.strip().startswith("{")]
    assert len(documents) == 3
    validator = Validator()
    for document in documents:
        assert document["persons"]["pointOfContact"]
        assert validator.validate(document, return_validation=True) is True