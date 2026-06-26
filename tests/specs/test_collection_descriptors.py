"""Every L1 collection descriptor validates against the descriptor schema."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).parent.parent.parent
DESCRIPTOR_DIR = REPO_ROOT / "catalog" / "collections"
SCHEMA_PATH = REPO_ROOT / "docs" / "specs" / "schemas" / "collection-descriptor.schema.json"

EXPECTED_DOMAINS = {
    "transcriptomics", "genomics", "proteomics", "metabolomics",
    "phenotyping", "imaging", "microbiome",
}


def _descriptor_paths() -> list[Path]:
    return sorted(DESCRIPTOR_DIR.glob("dataplant-*.yaml"))


def test_all_seven_omics_descriptors_exist():
    ids = {yaml.safe_load(p.read_text())["id"] for p in _descriptor_paths()}
    assert ids == {f"dataplant-{d}" for d in EXPECTED_DOMAINS}


@pytest.mark.parametrize("path", _descriptor_paths(), ids=lambda p: p.name)
def test_descriptor_validates_against_schema(path: Path):
    schema = json.loads(SCHEMA_PATH.read_text())
    descriptor = yaml.safe_load(path.read_text())
    errors = sorted(Draft202012Validator(schema).iter_errors(descriptor), key=str)
    assert not errors, [e.message for e in errors]


@pytest.mark.parametrize("path", _descriptor_paths(), ids=lambda p: p.name)
def test_query_rule_matches_domain(path: Path):
    descriptor = yaml.safe_load(path.read_text())
    domain = descriptor["id"].removeprefix("dataplant-")
    assert descriptor["query_rule"] == f"'{domain}' = ANY(omics_domains)"
    assert descriptor["axis"] == "omics"


import sys  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import generate_catalog as gen  # noqa: E402


def test_derive_view_name():
    assert gen.derive_view_name("dataplant-proteomics") == "arc_records_proteomics"
    assert gen.derive_view_name("dataplant-foo-bar") == "arc_records_foo_bar"


def test_build_view_sql():
    desc = {"id": "dataplant-imaging", "query_rule": "'imaging' = ANY(omics_domains)"}
    sql = gen.build_view_sql(desc)
    assert sql == (
        "CREATE OR REPLACE VIEW arc_records_imaging AS "
        "SELECT * FROM arc_records WHERE 'imaging' = ANY(omics_domains);"
    )


def test_build_resource_shape():
    desc = yaml.safe_load(
        (DESCRIPTOR_DIR / "dataplant-proteomics.yaml").read_text()
    )
    res = gen.build_resource(desc)
    assert res["type"] == "collection"
    assert res["providers"][0]["table"] == "arc_records_proteomics"
    assert res["providers"][0]["geom_field"] == "geom"
    assert res["providers"][0]["type"] == "record"
    assert res["extents"]["spatial"]["bbox"] == [-180, -90, 180, 90]
    assert "omics_domains" in res["providers"][0]["properties"]


def test_check_mode_reports_in_sync():
    # After generation (committed files present), --check must pass.
    assert gen.main(["--check"]) == 0
