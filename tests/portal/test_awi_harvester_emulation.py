"""Run AWI's own harvester against our own ListRecords output, fully offline.

This is the one check that proves their XML parsing path accepts our envelope.
Their fetch() supports file:// URLs and skips resumption for them, so no server
and no network are involved.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from oai.mapping import map_record
from oai.source import OaiRecord, format_oai_datetime
from oai.verbs import RepoConfig, handle
from tests.oai.conftest import FakeSource

BASE = "https://interplant.example/oai"


def _payload(identifier: str) -> dict:
    return {
        "id": identifier,
        "type": "Feature",
        "geometry": None,
        "time": {"interval": [None, None]},
        "properties": {
            "title": f"Title {identifier}",
            "description": "desc",
            "created": "2026-06-24T00:00:00Z",
            "uniqueId": "00000000-0000-5000-8000-000000000000",
            "harvester_version": "0.1.0",
            "arc_source_uri": f"https://git.nfdi4plants.org/x/{identifier}",
            "experiment_context": "lab",
            "record_quality": "partial",
            "harvested_at": "2026-06-24T00:00:00Z",
            "keywords": ["alpha"],
            "omics_domains": ["proteomics"],
            "organism": [],
            "project": [],
            "contacts": [],
            "creators": [],
            "publications": [],
            "assays": [],
            "studies": [],
        },
    }


def _record(identifier: str, day: int) -> OaiRecord:
    ts = datetime(2026, 6, day, tzinfo=UTC)
    return OaiRecord(
        identifier=identifier,
        datestamp=format_oai_datetime(ts),
        cursor_ts=ts,
        payload=_payload(identifier),
    )


def _write_list_records(tmp_path, records):
    xml = handle(
        {"verb": "ListRecords", "metadataPrefix": "documentschema"},
        base_url=BASE,
        source=FakeSource(list(records)),
        config=RepoConfig(),
    )
    path = tmp_path / "listrecords.xml"
    path.write_bytes(xml)
    return path


def _run(module, tmp_path, records, capsys):
    """Harvest the rendered response and return the documents printed to stdout."""
    path = _write_list_records(tmp_path, records)
    harvester = module.DataPlantArcHarvester(
        url=f"file://{path}",
        logfile=str(tmp_path / "harvest.log"),
    )
    # exit_on_exception=False so a failure raises here instead of sys.exit(1).
    harvester.harvest({"metadataPrefix": "documentschema"}, exit_on_exception=False)

    out = capsys.readouterr().out
    return [json.loads(ln) for ln in out.splitlines() if ln.strip().startswith("{")]


def test_awi_harvester_emits_one_document_per_record(awi_harvester_module, tmp_path, capsys):
    records = [_record(f"rec{i:02d}", i + 1) for i in range(3)]

    documents = _run(awi_harvester_module, tmp_path, records, capsys)

    assert len(documents) == 3, "the ingestion contract is one JSON document per line"


def test_emitted_documents_match_our_mapper_output(awi_harvester_module, tmp_path, capsys):
    """Their parser must hand our subclass the document our mapper built, unaltered."""
    records = [_record(f"rec{i:02d}", i + 1) for i in range(3)]

    documents = {d["id"]: d for d in _run(awi_harvester_module, tmp_path, records, capsys)}

    for record in records:
        expected = map_record(record.payload)
        produced = documents[expected["id"]]
        assert produced["uniqueId"] == expected["uniqueId"]
        assert produced["title"] == expected["title"]
        assert produced["resources"] == expected["resources"]
        assert produced["organisations"] == expected["organisations"]


def test_emitted_documents_carry_the_fleet_provenance_key(awi_harvester_module, tmp_path, capsys):
    """Their base prepare_record sets metadata._harvester; our override must too."""
    documents = _run(awi_harvester_module, tmp_path, [_record("rec00", 1)], capsys)

    assert documents[0]["metadata"]["_harvester"]


def test_emitted_documents_pass_the_portal_validator(awi_harvester_module, tmp_path, capsys):
    """Their Validator is deliberately stricter than their index server."""
    from helper.Validator import Validator

    documents = _run(awi_harvester_module, tmp_path, [_record("rec00", 1)], capsys)

    validator = Validator()
    for document in documents:
        assert validator.validate(document, return_validation=True) is True


def test_document_missing_a_mandatory_field_is_skipped_not_crashed(
    awi_harvester_module, tmp_path
):
    """Without our guard this reaches store_original_record and raises KeyError."""

    class _FakeElement:
        text = json.dumps({"id": "dataplant-x", "uniqueId": "u", "title": "T"})

    harvester = awi_harvester_module.DataPlantArcHarvester(
        url="file:///dev/null",
        logfile=str(tmp_path / "harvest.log"),
    )
    harvester.current_record = _FakeElement()

    assert harvester.prepare_record() is None, "a document with no resources must be skipped"
