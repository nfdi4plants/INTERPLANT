"""OAI-PMH metadata payload builders.

oai_dc: the mandatory Dublin Core baseline.
documentschema: carries the portal DocumentSchema JSON as the (XML-escaped) text of
a single namespaced element. Escaped text (not CDATA) is deliberate: ElementTree
escapes natively, there is no ]]> failure mode, and `element.text` yields the same
unescaped JSON a CDATA section would. This function is the one piece to swap once AWI
confirms the exact contract.

Author: Mohamed Abouzid m.abouzid@fz-juelich.de
"""
from __future__ import annotations

import json
from xml.etree.ElementTree import Element, SubElement, register_namespace

OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"
DC_NS = "http://purl.org/dc/elements/1.1/"
AWI_NS = "https://gitlab.awi.de/software-engineering/index/de.awi.index"
DOCSCHEMA_REF = (
    "https://gitlab.awi.de/software-engineering/index/de.awi.index/-/raw/master/"
    "DocumentSchema.json"
)

register_namespace("oai_dc", OAI_DC_NS)
register_namespace("dc", DC_NS)
register_namespace("awi", AWI_NS)


def oai_dc_element(record_payload: dict) -> Element:
    p = record_payload["properties"]
    root = Element(f"{{{OAI_DC_NS}}}dc")

    def dc(tag: str, text: str) -> None:
        SubElement(root, f"{{{DC_NS}}}{tag}").text = text

    dc("title", p["title"])
    if p.get("description"):
        dc("description", p["description"])
    dc("identifier", p["arc_source_uri"])
    dc("date", p["created"])
    for kw in p.get("keywords", []):
        dc("subject", kw)
    for domain in p.get("omics_domains", []):
        dc("subject", domain)
    dc("type", "dataset")
    return root


def documentschema_element(document: dict) -> Element:
    el = Element(f"{{{AWI_NS}}}document", {"schemaRef": DOCSCHEMA_REF})
    el.text = json.dumps(document, ensure_ascii=False, sort_keys=True)
    return el
