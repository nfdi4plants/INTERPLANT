"""Thin wrapper around `arctrl` returning plain dataclasses.

Only this module imports `arctrl`. The rest of the harvester operates on
the dataclasses below so it stays library-agnostic and trivially testable.

`arctrl` 3.0.5 returns assays at the ARC level (flat list), with each Study
holding `RegisteredAssayIdentifiers` (list of names) that link studies to
their registered assays. This reader joins the flat assay list back into
the per-study dataclasses below so downstream code can iterate
investigation.studies[i].assays[j] naturally.

Verified API notes (arctrl 3.0.5):
- arc.Studies / arc.Assays / arc.Contacts are flat lists on the ARC object.
- Study.RegisteredAssayIdentifiers is a list of assay identifier strings.
- Contact uses .EMail (not .Email).
- Assay.MeasurementType / TechnologyType / TechnologyPlatform are arctrl
  OntologyAnnotation objects, not plain strings. Use _annotation_name() to
  extract the .Name field; do NOT call str() on them directly.
- arc.Publications is a list of Publication objects with a .DOI attribute.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Identifier for the stub study synthesised when an ARC has assays but no
# studies at all (some ARCs register assays only at the ARC level).
_SYNTHETIC_STUDY_ID = "unregistered-assays"


@dataclass(frozen=True)
class Assay:
    name: str
    folder: str
    measurement_type: str | None
    technology_type: str | None = None


@dataclass(frozen=True)
class Study:
    identifier: str
    title: str | None
    assays: list[Assay]


@dataclass(frozen=True)
class Contact:
    first_name: str | None
    last_name: str | None
    email: str | None
    orcid: str | None
    affiliation: str | None


@dataclass(frozen=True)
class Investigation:
    identifier: str
    title: str
    description: str | None
    dois: list[str] = field(default_factory=list)
    contacts: list[Contact] = field(default_factory=list)
    studies: list[Study] = field(default_factory=list)
    organisms: list[str] = field(default_factory=list)
    license: str | None = None
    arc_root: Path | None = None


class IsaReader:
    """Read an ARC root directory and return a populated Investigation."""

    def read(self, arc_root: Path) -> Investigation:
        import arctrl

        arc = arctrl.ARC.load(str(arc_root))

        # arc.Assays is a flat list; _assemble_studies joins it onto the studies.
        assays = [_assay_from(raw) for raw in (arc.Assays or [])]
        study_specs = [
            (
                str(study.Identifier),
                _str_or_none(getattr(study, "Title", None)),
                list(getattr(study, "RegisteredAssayIdentifiers", []) or []),
            )
            for study in (arc.Studies or [])
        ]

        return Investigation(
            identifier=str(arc.Identifier or ""),
            title=str(arc.Title or ""),
            description=_str_or_none(getattr(arc, "Description", None)),
            dois=_dois_from(arc),
            contacts=[_contact_from(p) for p in (arc.Contacts or [])],
            studies=_assemble_studies(study_specs, assays),
            organisms=_organisms_from(arc),
            license=_license_from(arc),
            arc_root=arc_root,
        )


def _organisms_from(arc) -> list[str]:
    """Collect organism characteristic values across the ARC's studies.

    Confirmed by the Task 1 discovery spike: organism lives in study ArcTable
    columns whose header names an organism/species characteristic. Tolerant of
    header variants (Organism / organism / Species / species_short_names) but
    excludes 'organism part' (that is tissue, not organism). Defensive: any
    arctrl shape surprise yields [] rather than breaking ingest.
    """
    out: list[str] = []
    for study in (getattr(arc, "Studies", None) or []):
        for table in (getattr(study, "Tables", None) or []):
            out.extend(_organism_values_from_table(table))
    return out


def _organism_values_from_table(table) -> list[str]:
    try:
        headers = getattr(table, "Headers", None) or []
        columns = getattr(table, "Columns", None) or []
        values: list[str] = []
        for colidx, header in enumerate(headers):
            header_str = str(header).lower()
            if "part" in header_str:
                continue
            if "organism" not in header_str and "species" not in header_str:
                continue
            if colidx >= len(columns):
                continue
            for cell in (getattr(columns[colidx], "Cells", None) or []):
                text = _annotation_name(cell)
                if text:
                    values.append(text)
        return values
    except Exception:  # noqa: BLE001 - never let table parsing break ingest
        return []


def _license_from(arc) -> str | None:
    """Unwrap a license string from arctrl's arc.License object.

    AMENDED per the Task 1 discovery spike: arc.Comments is always empty on
    real ARCs, so the originally-planned investigation Comment[License] path
    does not exist. License lives in arc.License (an arctrl License object).
    Its attribute shape is not documented here, so we probe a few likely
    name-like attributes defensively; if none yield a value we return None and
    let extract_license() fall back to the root LICENSE file.
    """
    try:
        license_obj = getattr(arc, "License", None)
        if license_obj is None:
            return None
        for attr in ("Name", "FullName", "fullName", "SPDX", "spdx", "Id", "Identifier"):
            value = _str_or_none(getattr(license_obj, attr, None))
            if value:
                return value
        return None
    except Exception:  # noqa: BLE001 - never let license parsing break ingest
        return None


def _dois_from(arc) -> list[str]:
    # arc.Publications is a list of Publication objects; each has a .DOI attr.
    raw = getattr(arc, "Publications", None)
    if not raw:
        return []
    out: list[str] = []
    for p in raw:
        doi = getattr(p, "DOI", None) if not isinstance(p, str) else p
        if doi:
            out.append(str(doi))
    return out


def _contact_from(person) -> Contact:
    # arctrl 3.0.5 uses .EMail (not .Email) on the Person object.
    return Contact(
        first_name=_str_or_none(getattr(person, "FirstName", None)),
        last_name=_str_or_none(getattr(person, "LastName", None)),
        email=_str_or_none(getattr(person, "EMail", None)),
        orcid=_str_or_none(getattr(person, "ORCID", None)),
        affiliation=_str_or_none(getattr(person, "Affiliation", None)),
    )


def _assemble_studies(
    study_specs: list[tuple[str, str | None, list[str]]],
    assays: list[Assay],
) -> list[Study]:
    """Join assays onto studies, tolerating ARCs that never register them.

    `study_specs` is a list of (identifier, title, registered_assay_ids) tuples
    extracted from the ARC's studies. Many real ARCs leave the registered-assay
    list empty even though assays exist on disk (and in `arc.Assays`); in that
    case we attach the full assay list rather than silently dropping it. When an
    ARC has assays but no studies at all, we synthesise one stub study to carry
    them so downstream record-building still sees the assays.
    """
    if not study_specs:
        if not assays:
            return []
        return [Study(identifier=_SYNTHETIC_STUDY_ID, title=None, assays=list(assays))]

    assay_by_folder = {a.folder: a for a in assays}
    studies: list[Study] = []
    for identifier, title, registered in study_specs:
        if registered:
            attached = [assay_by_folder[name] for name in registered if name in assay_by_folder]
        else:
            # Registration column left empty: attach every assay rather than drop them.
            attached = list(assays)
        studies.append(Study(identifier=identifier, title=title, assays=attached))
    return studies


def _assay_from(assay) -> Assay:
    folder = str(getattr(assay, "Identifier", "")).strip()
    measurement_type = _annotation_name(getattr(assay, "MeasurementType", None))
    technology_type = _annotation_name(
        getattr(assay, "TechnologyType", None)
        or getattr(assay, "TechnologyPlatform", None)
    )
    return Assay(
        name=folder,
        folder=folder,
        measurement_type=measurement_type,
        technology_type=technology_type,
    )


def _annotation_name(value) -> str | None:
    """Return the .Name of an arctrl OntologyAnnotation, or the plain string.

    arctrl exposes MeasurementType/TechnologyType/TechnologyPlatform as
    OntologyAnnotation objects whose str() is '{Name = X; TSR = ...; TAN = ...}'.
    We want just X. Plain strings (used in tests/older paths) pass through.
    """
    if value is None:
        return None
    name = getattr(value, "Name", None)
    if name is not None:
        return _str_or_none(name)
    return _str_or_none(value)


def _str_or_none(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
