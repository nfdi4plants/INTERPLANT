"""Build the `data` dicts pygeoapi 0.23.4 passes to our templates.

Shapes are copied from api/itemtypes.py (HTML branch for the items list at
lines 663-683, single item at 1006-1019), api/__init__.py:977 for the
collection page, and live responses from the dev stack. Keep them in step
with pygeoapi: a key the templates read but pygeoapi never sets renders as
an empty string, not an error.
"""
from __future__ import annotations

import json
import re

BASE = "http://localhost:5000"
COLLECTION = "arc-records"
COLLECTION_URL = f"{BASE}/collections/{COLLECTION}"
ITEMS = f"{COLLECTION_URL}/items"

ITEM_TPL = "collections/items/item.html"
ITEMS_TPL = "collections/items/index.html"
COLLECTION_TPL = "collections/collection.html"

POINT = {"type": "Point", "coordinates": [6.7926, 51.1889]}
MULTIPOINT = {
    "type": "MultiPoint",
    "coordinates": [
        [11.27888, 51.826197],
        [101.13511, 12.73322],
        [-70.783333, -28.566667],
    ],
}


def record_properties(**overrides) -> dict:
    props = {
        "title": "Worked example record",
        "description": "A description of the worked example.",
        "created": "2026-09-22T02:01:15+00:00",
        "omics_domains": ["genomics", "imaging"],
        "experiment_context": "lab",
        "organism": ["Arabidopsis thaliana"],
        "keywords": [],
        "arc_source_uri": "https://git.nfdi4plants.org/example/worked-example",
        "contacts": [
            {
                "name": "Ada Lovelace",
                "roles": ["author"],
                "organization": "FZJ",
                "identifier": "https://orcid.org/0000-0002-1825-0097",
            },
            {"name": "No Orcid", "roles": ["author"], "organization": "HHU"},
        ],
        "externalIds": [
            {"value": "ef4702a2-deeb-51f6-8042-de011f4e4e5b", "scheme": "urn:uuid"}
        ],
    }
    props.update(overrides)
    return props


def feature(record_id: str = "dataplant-worked-example", geometry=None, **prop_overrides) -> dict:
    return {
        "type": "Feature",
        "id": record_id,
        "geometry": geometry,
        "properties": record_properties(**prop_overrides),
    }


def item_data(
    record_id: str = "dataplant-worked-example",
    geometry=None,
    prev: str | None = "dataplant-prev",
    next_: str | None = "dataplant-next",
    **prop_overrides,
) -> dict:
    href = f"{ITEMS}/{record_id}"
    data = feature(record_id, geometry, **prop_overrides)
    data.update(
        {
            "prev": prev,
            "next": next_,
            "links": [
                {"rel": "self", "type": "application/geo+json",
                 "title": "This document as JSON", "href": f"{href}?f=json"},
                {"rel": "alternate", "type": "application/ld+json",
                 "title": "This document as RDF (JSON-LD)", "href": f"{href}?f=jsonld"},
                {"rel": "alternate", "type": "text/html",
                 "title": "This document as HTML", "href": f"{href}?f=html"},
                {"rel": "collection", "type": "application/json",
                 "title": "INTERPLANT ARC records", "href": COLLECTION_URL},
            ],
            # itemtypes.py:1008 sets the collection title; no title_field is
            # configured for arc-records, so title_field is absent on purpose.
            "title": "INTERPLANT ARC records",
            "id_field": "id",
            "collections_path": f"{BASE}/collections",
        }
    )
    return data


def items_data(features: list[dict]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": features,
        "numberMatched": len(features),
        "numberReturned": len(features),
        "links": [
            {"type": "application/geo+json", "rel": "self",
             "title": "This document as GeoJSON", "href": f"{ITEMS}?f=json"},
            {"rel": "alternate", "type": "application/ld+json",
             "title": "This document as RDF (JSON-LD)", "href": f"{ITEMS}?f=jsonld"},
            {"type": "text/html", "rel": "alternate",
             "title": "This document as HTML", "href": f"{ITEMS}?f=html"},
            {"type": "application/json", "title": "INTERPLANT ARC records",
             "rel": "collection", "href": COLLECTION_URL},
        ],
        # itemtypes.py:667-670
        "itemtype": "record",
        "items_path": ITEMS,
        "dataset_path": COLLECTION_URL,
        "collections_path": f"{BASE}/collections",
        "offset": 0,
        "id_field": "id",
    }


def collection_data() -> dict:
    return {
        "id": COLLECTION,
        "title": "INTERPLANT ARC records",
        "description": "All harvested DataPLANT ARC metadata records.",
        "keywords": ["arc", "dataplant", "records"],
        "itemType": "record",
        "links": [
            {"type": "text/html", "rel": "canonical", "title": "DataPLANT",
             "href": "https://www.nfdi4plants.org/"},
            {"type": "application/geo+json", "rel": "items",
             "title": "Items as GeoJSON", "href": f"{ITEMS}?f=json"},
        ],
        # api/__init__.py:977
        "collections_path": f"{BASE}/collections",
    }


def dataset_jsonld(html: str) -> dict:
    """Return the page's single server-rendered schema.org Dataset block."""
    blocks = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
    )
    assert len(blocks) == 1, f"expected exactly one ld+json block, got {len(blocks)}"
    return json.loads(blocks[0])