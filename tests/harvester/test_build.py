"""Tests for harvester.build.build_record."""
from __future__ import annotations

import pytest

from harvester.build import build_record
from harvester.isa_reader import Assay, Contact, Investigation, Study


def _fake_investigation() -> Investigation:
    return Investigation(
        identifier="ArcPrototype",
        title="Prototype ARC",
        description="A prototypic ARC implementing all specs.",
        dois=["10.1234/example"],
        contacts=[
            Contact(
                first_name="Alex",
                last_name="Doe",
                email="alex@example.org",
                orcid=None,
                affiliation="Example University",
            )
        ],
        studies=[
            Study(
                identifier="experiment2",
                title="Experiment 2",
                assays=[],
            ),
            Study(
                identifier="MaterialPreparation",
                title="Material Preparation",
                assays=[
                    Assay(name="measurement1", folder="measurement1", measurement_type=None),
                    Assay(
                        name="RNA-Seq",
                        folder="RNA-Seq",
                        measurement_type="transcription profiling",
                    ),
                ],
            ),
        ],
    )


_CALL_KWARGS = {
    "arc_source_uri": "https://example.invalid/dataplant/arcprototype",
    "harvested_at":   "2026-05-21T12:00:00Z",
    "created":        "2026-01-01T00:00:00Z",
    "updated":        "2026-05-21T12:00:00Z",
}


def test_build_record_id_matches_provider_slug() -> None:
    record = build_record(
        _fake_investigation(),
        omics_by_folder={"RNA-Seq": "transcriptomics"},
        **_CALL_KWARGS,
    )
    assert record["id"] == "dataplant-arcprototype"


def test_build_record_validates_against_schema(validate_record) -> None:
    record = build_record(
        _fake_investigation(),
        omics_by_folder={"RNA-Seq": "transcriptomics"},
        **_CALL_KWARGS,
    )
    validate_record(record)


def test_build_record_top_level_shape() -> None:
    record = build_record(
        _fake_investigation(),
        omics_by_folder={"RNA-Seq": "transcriptomics"},
        **_CALL_KWARGS,
    )
    assert record["type"] == "Feature"
    assert record["geometry"] is None
    assert record["time"]["interval"] == [None, None]
    assert record["properties"]["uniqueId"]  # synthesized uuid
    assert record["properties"]["harvester_version"] == "0.1.0"


def test_build_record_collects_omics_domains() -> None:
    record = build_record(
        _fake_investigation(),
        omics_by_folder={"RNA-Seq": "transcriptomics"},
        **_CALL_KWARGS,
    )
    assert "transcriptomics" in record["properties"]["omics_domains"]


def test_build_record_assays_flat_at_properties() -> None:
    record = build_record(
        _fake_investigation(),
        omics_by_folder={"RNA-Seq": "transcriptomics"},
        **_CALL_KWARGS,
    )
    # Schema requires properties.assays to be a flat list with minItems: 1
    assert isinstance(record["properties"]["assays"], list)
    assert len(record["properties"]["assays"]) >= 1


def test_build_record_studies_listed_under_properties() -> None:
    record = build_record(
        _fake_investigation(),
        omics_by_folder={"RNA-Seq": "transcriptomics"},
        **_CALL_KWARGS,
    )
    study_ids = {s["id"] for s in record["properties"]["studies"]}
    assert study_ids == {"experiment2", "MaterialPreparation"}


def test_build_record_unmapped_omics_falls_back_safely() -> None:
    """A non-enum classifier value (e.g. a stale 'phenomics') must degrade to
    the schema-valid 'other' bucket so the record still validates, never crash."""
    record = build_record(
        _fake_investigation(),
        # 'phenomics' is not a schema enum value; it must map to 'other'.
        omics_by_folder={"RNA-Seq": "phenomics"},
        **_CALL_KWARGS,
    )
    domains = record["properties"]["omics_domains"]
    valid = {"transcriptomics", "genomics", "proteomics", "metabolomics",
             "phenotyping", "imaging", "microbiome", "other"}
    assert set(domains) <= valid
    assert domains == ["other"]


@pytest.mark.parametrize(
    "vocab_value",
    [
        "transcriptomics",
        "genomics",
        "proteomics",
        "metabolomics",
        "epigenomics",   # non-enum -> other
        "phenomics",     # non-enum -> other
    ],
)
def test_build_record_validates_for_every_omics_vocab_value(
    validate_record, vocab_value: str
) -> None:
    """Every vocab value the omics classifier can emit must produce a record that
    validates end-to-end (top-level + assay-extensions oneOf branch)."""
    record = build_record(
        _fake_investigation(),
        omics_by_folder={"RNA-Seq": vocab_value},
        **_CALL_KWARGS,
    )
    validate_record(record)


def test_build_record_unique_id_is_deterministic() -> None:
    """uniqueId must depend only on arc_source_uri (uuid5 of NAMESPACE_URL)."""
    a = build_record(
        _fake_investigation(),
        omics_by_folder={"RNA-Seq": "transcriptomics"},
        **_CALL_KWARGS,
    )
    b = build_record(
        _fake_investigation(),
        omics_by_folder={"RNA-Seq": "transcriptomics"},
        **_CALL_KWARGS,
    )
    assert a["properties"]["uniqueId"] == b["properties"]["uniqueId"]


def _rich_investigation(tmp_path) -> Investigation:
    arc_root = tmp_path / "arc"
    base = arc_root / "assays" / "RNA-Seq" / "dataset"
    base.mkdir(parents=True)
    (base / "r1.fastq").write_text("x", encoding="utf-8")
    return Investigation(
        identifier="ArcX",
        title="A greenhouse study of Arabidopsis",
        description="Plants grown in the greenhouse.",
        organisms=["Arabidopsis thaliana"],
        license="CC-BY-4.0",
        arc_root=arc_root,
        studies=[
            Study(
                identifier="s1",
                title="Greenhouse study",
                assays=[
                    Assay(
                        name="RNA-Seq",
                        folder="RNA-Seq",
                        measurement_type="transcription profiling",
                        technology_type="Illumina NovaSeq",
                    )
                ],
            )
        ],
    )


def test_build_enriches_core_fields(tmp_path) -> None:
    inv = _rich_investigation(tmp_path)
    record = build_record(inv, omics_by_folder={"RNA-Seq": "transcriptomics"}, **_CALL_KWARGS)
    props = record["properties"]
    assert props["organism"] == ["Arabidopsis thaliana"]
    assert props["license"] == "CC-BY-4.0"
    # experiment_context is DEMOTED (spike): always the "lab" stub.
    assert props["experiment_context"] == "lab"
    # record_quality core set = [omics, organism]; both present here -> complete.
    assert props["record_quality"] == "complete"
    assay = props["assays"][0]
    assert assay["technology_type"] == "Illumina NovaSeq"
    assert assay["file_counts"] == {"raw": 1, "derived": 0}


def test_build_falls_back_and_marks_partial() -> None:
    # No organisms, no license, no arc_root, no omics -> all stubs, partial.
    inv = Investigation(identifier="Bare", title="bare", description=None,
                        studies=[Study(identifier="s", title="s", assays=[])])
    record = build_record(inv, omics_by_folder={}, **_CALL_KWARGS)
    props = record["properties"]
    assert props["organism"] == []
    assert props["license"] == "unknown"
    assert props["experiment_context"] == "lab"
    assert props["record_quality"] == "partial"
