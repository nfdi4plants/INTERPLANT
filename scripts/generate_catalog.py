"""Generate catalog SQL views and pygeoapi resources from L1 descriptors.

Single source of truth: catalog/collections/*.yaml. Run `make catalog-gen` (or
`python scripts/generate_catalog.py`) to refresh the committed generated files.
`--check` regenerates in memory and exits non-zero if the committed files differ.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
DESCRIPTOR_DIR = REPO_ROOT / "catalog" / "collections"
SCHEMA_PATH = REPO_ROOT / "docs" / "specs" / "schemas" / "collection-descriptor.schema.json"
SQL_OUT = REPO_ROOT / "sql" / "catalog_collections.generated.sql"
CONFIG_BASE = REPO_ROOT / "pygeoapi-config.base.yml"
CONFIG_OUT = REPO_ROOT / "pygeoapi-config.yml"

_GENERATED_NOTE = (
    "# GENERATED FILE - do not edit. Edit catalog/collections/*.yaml or\n"
    "# pygeoapi-config.base.yml and run `make catalog-gen`.\n"
)
LOCATIONS_DESCRIPTOR = DESCRIPTOR_DIR / "arc-locations.yaml"
_LOCATION_PROPERTIES = ["record_id", "role", "label", "precision", "n_rows", "source"]
_SQL_NOTE = (
    "-- GENERATED FILE - do not edit. Edit catalog/collections/*.yaml and run\n"
    "-- `make catalog-gen`. Per-domain filter views over the base arc_records view.\n"
)
_PROPERTIES = [
    "title", "description", "created", "omics_domains",
    "experiment_context", "organism", "keywords", "arc_source_uri",
]
_DB = {
    "host": "db", "port": 5432, "dbname": "interplant",
    "user": "interplant", "password": "interplant",
}


def load_descriptors() -> list[dict]:
    return [yaml.safe_load(p.read_text()) for p in sorted(DESCRIPTOR_DIR.glob("dataplant-*.yaml"))]


def validate(descriptors: list[dict]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    validator = Draft202012Validator(schema)
    for desc in descriptors:
        errors = sorted(validator.iter_errors(desc), key=str)
        if errors:
            msgs = "; ".join(e.message for e in errors)
            raise SystemExit(f"invalid descriptor {desc.get('id', '?')}: {msgs}")


def derive_view_name(descriptor_id: str) -> str:
    return "arc_records_" + descriptor_id.removeprefix("dataplant-").replace("-", "_")


def build_view_sql(descriptor: dict) -> str:
    view = derive_view_name(descriptor["id"])
    return (
        f"CREATE OR REPLACE VIEW {view} AS "
        f"SELECT * FROM arc_records WHERE {descriptor['query_rule']};"
    )


def build_resource(descriptor: dict) -> dict:
    view = derive_view_name(descriptor["id"])
    return {
        "type": "collection",
        "title": descriptor["title"],
        "description": descriptor["description"].strip(),
        "keywords": list(descriptor["keywords"]),
        "extents": {
            "spatial": {
                "bbox": list(descriptor["extent"]["spatial"]["bbox"][0]),
                "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
            }
        },
        "links": [
            {
                "type": "text/html",
                "rel": "canonical",
                "title": "DataPLANT",
                "href": "https://www.nfdi4plants.org/",
            }
        ],
        "providers": [
            {
                "type": "record",
                "name": "PostgreSQL",
                "data": dict(_DB),
                "id_field": "id",
                "table": view,
                "geom_field": "geom",
                "properties": list(_PROPERTIES),
            }
        ],
    }


def build_locations_resource(descriptor: dict) -> dict:
    """pygeoapi resource for the arc_locations view.

    A `feature` provider, not `record`: this collection serves geodata, one
    Feature per point, and has no omics query_rule. The extent stays
    world-wide, deliberately - see docs/specs/collection-schema.md.
    """
    return {
        "type": "collection",
        "title": descriptor["title"],
        "description": descriptor["description"].strip(),
        "keywords": descriptor["keywords"],
        "extents": {
            "spatial": {
                "bbox": list(descriptor["extent"]["spatial"]["bbox"][0]),
                "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
            }
        },
        "links": [],
        "providers": [
            {
                "type": "feature",
                "name": "PostgreSQL",
                "data": dict(_DB),
                "id_field": "id",
                "table": "arc_locations",
                "geom_field": "geom",
                "properties": list(_LOCATION_PROPERTIES),
            }
        ],
    }


def render_sql(descriptors: list[dict]) -> str:
    lines = [build_view_sql(d) for d in descriptors]
    return _SQL_NOTE + "\n" + "\n".join(lines) + "\n"


def render_config(descriptors: list[dict], base_text: str) -> str:
    blocks = []
    for desc in descriptors:
        block = yaml.safe_dump(
            {desc["id"]: build_resource(desc)},
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
            width=1000,
        )
        blocks.append("  " + block.replace("\n", "\n  ").rstrip() + "\n")
    if LOCATIONS_DESCRIPTOR.exists():
        locations = yaml.safe_load(LOCATIONS_DESCRIPTOR.read_text())
        block = yaml.safe_dump(
            {locations["id"]: build_locations_resource(locations)},
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
            width=1000,
        )
        blocks.append("  " + block.replace("\n", "\n  ").rstrip() + "\n")
    return _GENERATED_NOTE + base_text.rstrip() + "\n" + "".join(blocks)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    check = "--check" in argv
    descriptors = load_descriptors()
    validate(descriptors)
    sql = render_sql(descriptors)
    config = render_config(descriptors, CONFIG_BASE.read_text())
    if check:
        stale = []
        if not SQL_OUT.exists() or SQL_OUT.read_text() != sql:
            stale.append(str(SQL_OUT.relative_to(REPO_ROOT)))
        if not CONFIG_OUT.exists() or CONFIG_OUT.read_text() != config:
            stale.append(str(CONFIG_OUT.relative_to(REPO_ROOT)))
        if stale:
            print("out of sync (run make catalog-gen): " + ", ".join(stale))
            return 1
        print("catalog generated files in sync")
        return 0
    SQL_OUT.write_text(sql)
    CONFIG_OUT.write_text(config)
    print(f"wrote {SQL_OUT.name} and {CONFIG_OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
