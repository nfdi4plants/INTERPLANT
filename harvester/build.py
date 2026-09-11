"""Assemble an L2 record dict from an Investigation + omics classifier results.

The output validates against docs/specs/schemas/record.schema.json (Draft 2020-12)
together with the assay-extensions.schema.json referenced inside it.

Plan 4 enrichment status (as of Task 8):
- organism:           extracted via extractors.organism.extract_organisms.
- license:            extracted via extractors.license.extract_license.
- technology_type:    read from Assay.technology_type (parsed by IsaReader).
- file_counts:        counted via extractors.file_counts.count_assay_files.
- record_quality:     computed from core set [omics, organism]; "complete" when
                      both are present, "partial" otherwise.
- experiment_context: DEMOTED per Task 1 discovery spike - usable field/greenhouse/lab
                      wording appeared in <20% of real ARCs. Always the "lab" stub.
- domain-specific extension fields (library_strategy, platform, ...): still skeleton
  defaults - deriving them from ARC assay metadata is out of scope for Plan 4.
"""
from __future__ import annotations

import uuid
from typing import Any

from harvester.extractors.file_counts import count_assay_files
from harvester.extractors.license import extract_license
from harvester.extractors.location import derive_geometry, resolve_locations
from harvester.extractors.organism import extract_organisms
from harvester.ids import mint_id
from harvester.isa_reader import Investigation

_SCHEMA_ENUM_VALUES = frozenset({
    "transcriptomics", "genomics", "proteomics", "metabolomics",
    "phenotyping", "imaging", "microbiome", "other",
})


def _map_domain(raw: str | None) -> str:
    """Validate a classifier domain against the schema enum.

    The classifier now emits schema-enum values directly; this is a defensive
    guard so any unexpected/stale value degrades to "other" instead of
    producing an invalid record.
    """
    if raw in _SCHEMA_ENUM_VALUES:
        return raw
    return "other"


# ---------------------------------------------------------------------------
# Per-domain skeleton extension fields required by assay-extensions.schema.json
#
# The extensions schema uses oneOf: each assay must satisfy exactly one branch.
# Each branch requires "domain" plus domain-specific fields.  These skeleton
# values are placeholders; Plan 4 will derive real values from ARC metadata.
# ---------------------------------------------------------------------------
def _extension_fields(domain: str) -> dict[str, Any]:
    """Return the skeleton domain-extension fields required by assay-extensions.schema.json."""
    if domain == "transcriptomics":
        return {
            "library_strategy": "other",   # Plan 4: derive from ARC assay metadata
            "platform":         "OTHER",    # Plan 4: derive from ARC assay metadata
        }
    if domain == "genomics":
        return {
            "library_strategy": "other",   # Plan 4: derive from ARC assay metadata
            "platform":         "OTHER",    # Plan 4: derive from ARC assay metadata
        }
    if domain == "proteomics":
        return {
            "acquisition_mode": "other",   # Plan 4: derive from ARC assay metadata
        }
    if domain == "metabolomics":
        return {
            "chromatography": "other",     # Plan 4: derive from ARC assay metadata
            "ion_mode":       "positive",  # Plan 4: derive from ARC assay metadata
        }
    if domain == "phenotyping":
        return {
            "trait_category": "morphological",  # Plan 4: derive from ARC assay metadata
        }
    if domain == "imaging":
        return {
            "image_format": "other",       # Plan 4: derive from ARC assay metadata
        }
    if domain == "microbiome":
        return {
            "target_gene": "other",        # Plan 4: derive from ARC assay metadata
        }
    # domain == "other" (or any unexpected value): no extra fields required.
    return {}


def _build_assay(assay, domain: str, file_counts: dict[str, int]) -> dict[str, Any]:
    """Build a single assay dict satisfying AssayCore + assay-extensions.schema.json."""
    record: dict[str, Any] = {
        "id":               assay.folder,
        "domain":           domain,
        "technology_type":  assay.technology_type or "unknown",
        "measurement_type": assay.measurement_type or "unknown",
        "file_counts":      file_counts,
    }
    record.update(_extension_fields(domain))
    return record


def _build_person(contact) -> dict[str, Any]:
    """Build a Person dict from a Contact dataclass.

    Person schema requires 'name' (minLength 1).  ORCID must match the 16-digit
    pattern; skip it if the value doesn't look valid.
    """
    parts = [contact.first_name or "", contact.last_name or ""]
    name = " ".join(p for p in parts if p).strip()
    if not name:
        name = contact.email or "Unknown"

    person: dict[str, Any] = {"name": name}
    if contact.affiliation:
        person["affiliation"] = contact.affiliation
    if contact.orcid:
        # Basic sanity: schema pattern is ^[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9X]{3}[0-9X]$
        import re
        if re.match(r"^[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9X]{4}$", contact.orcid):
            person["orcid"] = contact.orcid
    return person


def build_record(
    investigation: Investigation,
    omics_by_folder: dict[str, str],
    *,
    arc_source_uri: str,
    harvested_at: str,
    created: str,
    updated: str,
    provider: str = "dataplant",
) -> dict[str, Any]:
    """Assemble an L2 record dict that validates against record.schema.json.

    Parameters
    ----------
    investigation:
        Parsed ARC metadata (from IsaReader.read).
    omics_by_folder:
        Mapping from assay-folder name to classifier output. The classifier
        emits schema-enum values directly; _map_domain guards against any stale
        or unexpected value by degrading it to "other".
    arc_source_uri:
        Canonical URI for the ARC repository (caller-provided; format: uri).
    harvested_at:
        ISO-8601 date-time string marking when harvesting ran.
    created:
        ISO-8601 date-time string for the record's creation timestamp.
    updated:
        ISO-8601 date-time string for the record's last-updated timestamp.
    provider:
        ARC registry provider slug (default "dataplant").
    """
    record_id = mint_id(provider, investigation.identifier)

    # Deterministic UUID from the canonical source URI so re-harvesting the
    # same ARC always yields the same uniqueId.
    unique_id = str(uuid.uuid5(uuid.NAMESPACE_URL, arc_source_uri))

    # ------------------------------------------------------------------
    # Collect all assays across all studies into a flat list.
    # omics_by_folder maps folder -> raw vocab value; we normalise to enum.
    # ------------------------------------------------------------------
    arc_root = investigation.arc_root
    all_assays: list[dict[str, Any]] = []
    seen_domains: list[str] = []

    # Deduplicate assay folders in case the same assay appears in multiple studies.
    seen_folders: set[str] = set()
    for study in investigation.studies:
        for assay in study.assays:
            if assay.folder in seen_folders:
                continue
            seen_folders.add(assay.folder)
            raw_domain = omics_by_folder.get(assay.folder)
            # _map_domain passes through valid enum values and degrades stale ones.
            domain = _map_domain(raw_domain)
            counts = (
                count_assay_files(arc_root, assay.folder)
                if arc_root is not None
                else {"raw": 0, "derived": 0}
            )
            all_assays.append(_build_assay(assay, domain, counts))
            seen_domains.append(domain)

    # Schema requires properties.assays to have minItems: 1.  If no assays were
    # found (e.g. all studies have empty assay lists), synthesise a placeholder.
    if not all_assays:
        placeholder = {
            "id":               "unknown",
            "domain":           "other",
            "technology_type":  "unknown",
            "measurement_type": "unknown",
            "file_counts":      {"raw": 0, "derived": 0},
        }
        all_assays.append(placeholder)
        seen_domains.append("other")

    # Deduplicated list of domains (preserving first-seen order) with minItems: 1.
    omics_domains: list[str] = []
    for d in seen_domains:
        if d not in omics_domains:
            omics_domains.append(d)
    if not omics_domains:
        omics_domains = ["other"]

    # ------------------------------------------------------------------
    # Studies
    # ------------------------------------------------------------------
    studies: list[dict[str, Any]] = [
        {
            "id":    s.identifier,
            "title": s.title or s.identifier,
        }
        for s in investigation.studies
    ]

    # ------------------------------------------------------------------
    # Contacts and creators - both populated from investigation.contacts.
    # ------------------------------------------------------------------
    persons = [_build_person(c) for c in investigation.contacts]

    # ------------------------------------------------------------------
    # Publications
    # ------------------------------------------------------------------
    publications: list[dict[str, Any]] = []
    for doi in investigation.dois:
        pub: dict[str, Any] = {"title": f"Publication ({doi})"}
        if doi.startswith("10."):
            pub["doi"] = doi
        publications.append(pub)

    # ------------------------------------------------------------------
    # Enriched record-level fields (Plan 4 Task 8)
    # ------------------------------------------------------------------
    organism = extract_organisms(investigation)
    license_value = (
        extract_license(investigation, arc_root) if arc_root is not None
        else (investigation.license.strip() if investigation.license else None)
    )

    # experiment_context DEMOTED per Task 1 spike: no classifier, always "lab" stub.
    # Usable field/greenhouse/lab wording appeared in <20% of real ARCs.
    context = None

    # record_quality: "complete" only when every core discovery field was
    # genuinely extracted (real value, not a stub fallback). Per the spike's
    # DEMOTE decision the core set is [omics, organism] - experiment_context
    # is excluded because it is not reliably extractable.
    core_extracted = [
        bool(omics_by_folder),   # omics: at least one real classification
        bool(organism),          # organism: non-empty
    ]
    record_quality = "complete" if all(core_extracted) else "partial"

    # ------------------------------------------------------------------
    # Locations and geometry
    #
    # locations[] carries every point found, from all tiers; geometry and
    # location_status reflect only the winning tier of the precedence chain
    # (extracted > geocoded > institution > absent). Measured coverage:
    # about 77% of ARCs resolve to a point, 23% stay null.
    # ------------------------------------------------------------------
    locations, location_status = resolve_locations(
        investigation, arc_source_uri=arc_source_uri
    )
    geometry = derive_geometry(locations, location_status)

    # ------------------------------------------------------------------
    # Assemble the record
    # ------------------------------------------------------------------
    return {
        "id":         record_id,
        "type":       "Feature",
        "conformsTo": ["https://interplant.org/schemas/record.schema.json"],
        "time":       {"interval": [None, None]},
        "geometry":   geometry,
        "properties": {
            "title":              investigation.title or investigation.identifier,
            "description":        investigation.description or "",
            "created":            created,
            "updated":            updated,
            "keywords":           [],
            "license":            license_value or "unknown",
            "arc_source_uri":     arc_source_uri,
            "uniqueId":           unique_id,
            "record_quality":     record_quality,
            "location_status":    location_status,
            "locations":          locations,
            "harvested_at":       harvested_at,
            "harvester_version":  "0.1.0",
            "contacts":           persons,
            "creators":           [],
            "publications":       publications,
            "omics_domains":      omics_domains,
            # experiment_context DEMOTED: always "lab" stub (see module docstring).
            "experiment_context": context or "lab",
            "organism":           organism,
            "project":            [],
            "studies":            studies,
            "assays":             all_assays,
        },
        "links": [],
    }
