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


# Duplicated from harvester.extractors.location's _TIER_BY_ROLE / tier_of:
# harvester/ is deliberately not part of the oai image (oai/Dockerfile only
# COPYs oai/), so this module cannot import it. Keep this in sync with the
# original - it is the same precedence table, extracted > geocoded >
# institution, first available tier wins.
_TIER_BY_ROLE = {
    "stated-place": "geocoded",
    "custodian-institution": "institution",
}
_TIER_ORDER = ("extracted", "geocoded", "institution")


def _tier_of(role: str) -> str:
    return _TIER_BY_ROLE.get(role, "extracted")


def _geometry_by_study(locations: list[dict], status: str) -> dict[str, dict]:
    """Group location points by the study identifier(s) in their source path.

    A source segment reads "studies/<identifier>/isa.study.xlsx#<sheet>", so
    its second path segment attributes a point to a study. An identical
    (role, point) seen in several tables is merged by
    harvester.extractors.location.points_from_tables, which joins the
    contributing tables' source paths with "; " - so one location's source
    can name several studies (or a mix of studies and assays), and every
    segment must be parsed independently rather than only the first. Points
    whose source has no studies/ segment at all (assays only, or a fallback
    tier: "affiliation" or a place-name source) carry no study attribution
    and stay on the record only.

    The precedence chain (extracted > geocoded > institution) is applied PER
    STUDY, not against the record's winning tier: a study whose own points
    are all in a tier that lost at the record level still has a best tier of
    its own, and must be admitted as that tier rather than excluded and
    falling back to a DIFFERENT study's record-level geometry (M1). `status`
    is only used for the "absent" short-circuit below - "absent" means
    resolve_locations found no points anywhere, so there is nothing to group.
    """
    if status == "absent":
        return {}
    by_study: dict[str, list[tuple[str, list[float]]]] = {}
    for loc in locations:
        tier = _tier_of(loc["role"])
        source = loc.get("source") or ""
        point = [float(loc["point"][0]), float(loc["point"][1])]
        for segment in source.split("; "):
            if not segment.startswith("studies/"):
                continue
            parts = segment.split("/")
            if len(parts) < 2 or not parts[1]:
                continue
            by_study.setdefault(parts[1], []).append((tier, point))

    out: dict[str, dict] = {}
    for study_id, tiered_points in by_study.items():
        present = {tier for tier, _ in tiered_points}
        best_tier = next((t for t in _TIER_ORDER if t in present), None)
        if best_tier is None:
            continue
        coords: list[list[float]] = []
        for tier, point in tiered_points:
            if tier == best_tier and point not in coords:
                coords.append(point)
        coords.sort()
        out[study_id] = (
            {"type": "Point", "coordinates": coords[0]}
            if len(coords) == 1
            else {"type": "MultiPoint", "coordinates": coords}
        )
    return out


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

    study_geometry = _geometry_by_study(
        p.get("locations", []), p.get("location_status", "absent")
    )

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
        # Per-study geometry where the points name a study; otherwise the
        # record geometry. Closes the v2 item parked in portal-mapping.md.
        own = study_geometry.get(study["id"])
        if own is not None:
            event["geometry"] = own
        elif record.get("geometry"):
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
