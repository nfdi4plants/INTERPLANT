"""Metadata format builders: oai_dc and the documentschema JSON-in-XML wrapper."""
from __future__ import annotations

import json
from xml.etree.ElementTree import tostring

from oai.formats import AWI_NS, DC_NS, OAI_DC_NS, documentschema_element, oai_dc_element


def _payload():
    return {
        "properties": {
            "title": "Heat & stress",
            "description": "d",
            "created": "2026-06-24T00:00:00Z",
            "arc_source_uri": "https://example.org/a",
            "keywords": ["k1"],
            "omics_domains": ["proteomics"],
        }
    }


def test_oai_dc_has_dc_children():
    el = oai_dc_element(_payload())
    assert el.tag == f"{{{OAI_DC_NS}}}dc"
    titles = el.findall(f"{{{DC_NS}}}title")
    assert len(titles) == 1 and titles[0].text == "Heat & stress"
    subjects = [s.text for s in el.findall(f"{{{DC_NS}}}subject")]
    assert "k1" in subjects and "proteomics" in subjects


def test_documentschema_text_roundtrips_to_input_json():
    doc = {"id": "x", "title": "a & b", "nested": {"k": [1, 2]}}
    el = documentschema_element(doc)
    assert el.tag == f"{{{AWI_NS}}}document"
    assert json.loads(el.text) == doc


def test_documentschema_serializes_with_escaped_ampersand():
    el = documentschema_element({"t": "a & b"})
    xml = tostring(el, encoding="unicode")
    assert "&amp;" in xml and "]]>" not in xml
