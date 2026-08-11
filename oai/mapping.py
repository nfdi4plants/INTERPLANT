"""Production mapper: INTERPLANT L2 record -> portal DocumentSchema document.

Pinned by tests/specs/test_portal_mapping.py against portal-document-schema.json.
Governed by docs/specs/portal-mapping.md.
"""
from __future__ import annotations

import copy
from typing import Any

# Constant per record. AWI confirmed we populate this ourselves rather than them
# adding a services.yaml entry for us. Provider is the source repository, datacenter
# is the institution operating the service - the same split their
# harvest-repository-fzj-publications.py uses. Kept in sync with
# portal/services.yaml.fragment.
ORGANISATIONS: dict[str, list[dict[str, Any]]] = {
    "provider": [
        {
            "abbreviation": "DataPLANT",
            "name": "DataPLANT - NFDI for Plant Sciences",
            "url": "https://nfdi4plants.org/",
        }
    ],
    "datacenter": [
        {
            "abbreviation": "FZJ",
            "name": "Forschungszentrum Jülich",
            "url": "https://www.fz-juelich.de/",
        }
    ],
}


def map_record(record: dict[str, Any]) -> dict[str, Any]:
    p = record["properties"]

    identifiers = []
    if "doi" in p:
        identifiers.append({"type": "doi", "id": p["doi"]})

    keywords: dict[str, list[dict]] = {}
    if p.get("keywords"):
        keywords["topics"] = [
            {"type": "topic", "name": k, "description": ""} for k in p["keywords"]
        ]
    if p.get("omics_domains"):
        keywords["omics"] = [
            {"type": "omics", "name": d, "description": ""} for d in p["omics_domains"]
        ]
    keywords["contexts"] = [
        {"type": "context", "name": p["experiment_context"], "description": ""}
    ]
    if p.get("organism"):
        keywords["organisms"] = [
            {"type": "organism", "name": o, "description": ""} for o in p["organism"]
        ]
    if p.get("project"):
        keywords["projects"] = [
            {"type": "project", "name": pr, "description": ""} for pr in p["project"]
        ]

    persons: dict[str, list[dict]] = {}
    for contact in p.get("contacts", []):
        role = contact.get("role", "pointOfContact")
        persons.setdefault(role, []).append(_person(contact, role))
    for creator in p.get("creators", []):
        persons.setdefault("author", []).append(_person(creator, "author"))

    devices = [
        {
            "id": a["id"],
            "name": a.get("instrument_name", a["domain"]),
            "type": "instrument",
            "metadata": {"domain": a["domain"]},
        }
        for a in p.get("assays", [])
    ]

    events: list[dict] = []
    for study in p.get("studies", []):
        event: dict[str, Any] = {
            "id": study["id"],
            "type": "study",
        }
        if record.get("time", {}).get("interval", [None, None])[0]:
            event["begin"] = record["time"]["interval"][0]
        if record.get("time", {}).get("interval", [None, None])[1]:
            event["end"] = record["time"]["interval"][1]
        if record.get("geometry"):
            event["geometry"] = record["geometry"]
        events.append(event)

    resources = []
    resources.append({
        "title": "ARC source",
        "type": "relation",
        "uri": p["arc_source_uri"],
        "metadata": {"relationType": "source"},
    })
    for pub in p.get("publications", []):
        if "doi" in pub:
            resources.append({
                "title": pub["title"],
                "type": "relation",
                "uri": f"https://doi.org/{pub['doi']}",
                "metadata": {"relationType": "isDocumentedBy"},
            })

    out: dict[str, Any] = {
        "uniqueId": p["uniqueId"],
        "id":       record["id"],
        "title":       p["title"],
        "description": p["description"],
        "date":        p["created"],
        "genericType": "data",
        "version":     p["harvester_version"],
        "identifiers": identifiers,
        "keywords":    keywords,
        "platforms":   [],
        "devices":     devices,
        "expeditions": [],
        "events":      events,
        "persons":     persons,
        "organisations": copy.deepcopy(ORGANISATIONS),
        "resources":   resources,
        "metadata": {
            "record_quality": p["record_quality"],
            "harvested_at":   p["harvested_at"],
        },
    }

    if record.get("time", {}).get("interval"):
        lower, upper = record["time"]["interval"]
        if lower and upper:
            out["temporalCoverage"] = {"lower": lower, "upper": upper}

    if record.get("geometry") is not None:
        out["geometry"] = record["geometry"]

    return out


def _person(person: dict[str, Any], role: str) -> dict[str, Any]:
    return {
        "role": role,
        "fullname": person["name"],
        "identifiers": (
            {"orcid": person["orcid"]} if "orcid" in person else {}
        ),
    }
