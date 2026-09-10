"""Extract georeferenced locations from parsed ARC tables.

Pure functions only: no I/O, no network, and never an `arctrl` import. The
caller supplies plain `harvester.isa_reader.Table` objects.

Value formats, header vocabularies and false-positive traps encoded here were
all measured across the 232 public ARCs; see
docs/progress/2026-09-09-location-coverage-report.md. Do not "simplify" the
deny list or the format regex without re-measuring: an early pass using loose
substring matching over-counted place names by a factor of four.
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Literal

from harvester.geo_roles import role_for_arc
from harvester.geo_tables import load_institutions, load_places, lookup

if TYPE_CHECKING:
    from harvester.isa_reader import Table

logger = logging.getLogger(__name__)

# Rounding applied before grouping and output: about 0.1 m, and the precision
# the corpus itself uses.
_PRECISION_DP = 6

_AXIS_LIMIT = {"lat": 90.0, "lon": 180.0}

# One number with an optional degree symbol, optional minutes and seconds, and
# an optional hemisphere letter. Accepts a leading + or -, and , or . as the
# decimal separator.
_COORD_VALUE = re.compile(
    r"""^\s*
    (?P<sign>[+-])?
    (?P<deg>\d+(?:[.,]\d+)?)\s*°?\s*
    (?:(?P<min>\d+(?:[.,]\d+)?)\s*['′]\s*)?
    (?:(?P<sec>\d+(?:[.,]\d+)?)\s*["″]\s*)?
    (?P<hemi>[NSEWnsew])?
    \s*$""",
    re.VERBOSE,
)


def parse_coord(raw: object, *, axis: Literal["lat", "lon"]) -> float | None:
    """Parse one cell into a signed decimal degree, or None if unusable.

    `axis` ("lat" or "lon") selects the range check; an unrecognised axis
    returns None rather than raising. A trailing N/S/E/W sets the sign and
    overrides any leading sign, because "70°47′ W" is negative longitude and
    a naive float() would place it in the eastern hemisphere. A hemisphere
    letter that contradicts the axis (N/S in a longitude column, E/W in a
    latitude column) is the strongest available signal of a swapped or
    mislabelled column, so it is rejected rather than accepted as a
    plausible-looking wrong coordinate.
    """
    limit = _AXIS_LIMIT.get(axis)
    if limit is None:
        return None
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    match = _COORD_VALUE.match(text)
    if match is None:
        return None

    def _num(group: str | None) -> float:
        return float(group.replace(",", ".")) if group else 0.0

    try:
        value = _num(match.group("deg"))
        value += _num(match.group("min")) / 60.0
        value += _num(match.group("sec")) / 3600.0
    except ValueError:
        return None

    hemi = (match.group("hemi") or "").upper()
    if hemi in ("N", "S") and axis != "lat":
        return None
    if hemi in ("E", "W") and axis != "lon":
        return None
    if hemi in ("S", "W"):
        value = -value
    elif hemi in ("N", "E"):
        pass
    elif match.group("sign") == "-":
        value = -value

    if not -limit <= value <= limit:
        return None
    return round(value, _PRECISION_DP)


# ---------------------------------------------------------------------------
# Header classification
#
# Matching is on header TEXT, case-insensitively. Coordinate columns carry no
# ontology annotation even when their siblings do (Teosinte: Parameter
# [Species] has MIAPPE:0043, Parameter [latitude] has nothing), so an
# accession-based lookup finds nothing.
# ---------------------------------------------------------------------------

# Both spellings of Characteristic: the corpus uses the SINGULAR
# ("Characteristic [latitude]" in MARS_ENA-Metabolights and DAP_Seq), so
# matching only the plural silently drops those ARCs.
_WRAPPER = re.compile(
    r"^\s*(?:parameter|characteristic|characteristics|factor|comment|component)"
    r"\s*\[(?P<core>.+)\]\s*$",
    re.IGNORECASE,
)

# arctrl folds Term Source REF / Term Accession Number / Unit into the header
# object, so they do not appear in Table.headers on that path. Kept as a guard
# for any caller reading raw xlsx.
_NON_HEADER = re.compile(r"^\s*(?:term source ref|term accession number|unit)\b", re.IGNORECASE)

_ROLE_BY_HEADER_PREFIX = (
    ("geographic location (lat", "experiment-site"),
    ("geographic location (lon", "experiment-site"),
    ("biological material lat", "material-origin"),
    ("biological material lon", "material-origin"),
    ("material source lat", "material-source"),
    ("material source lon", "material-source"),
    ("collection lat", "collection-site"),
    ("collection lon", "collection-site"),
)

# Whole-word place terms, matched against tokenised header text. Deliberately
# NOT substring-matched: see _PLACE_DENY.
#
# "area", "origin" and "state" are deliberately absent. Re-measured against
# every place header in the 14 place-name ARCs
# (docs/progress/2026-09-09-location-coverage-report.md:176-191): all of them
# are already satisfied by "location", "country", or a _PLACE_PHRASES entry,
# so those three words carry zero measured true positives - and each has a
# real plant/omics false-positive class ("area": leaf/surface/root area, area
# under curve; "origin": replication origin, vector origin; "state": sample
# state, developmental state).
_PLACE_WORDS = frozenset({
    "country", "pais", "país", "estado", "province", "region",
    "locality", "city", "ciudad", "town", "village", "municipality",
    "county", "district", "standort", "geographic", "location",
})

# Multi-word place phrases, substring-matched after the deny list.
_PLACE_PHRASES = (
    "geographic location", "geographic area", "experimental site name",
    "country code", "country_or_area", "collection site", "sampling site",
    "field site", "site name",
)

# Measured false positives, matched by TOKEN SUBSET (see _PLACE_DENY_TOKENS):
# a header is denied when a deny entry's own token set is a subset of the
# header's tokens, so a suffixed or annotated variant of a denied base -
# "Coding region 1", "sample state (fresh/frozen)", "Data location URL" - is
# denied too, not just the exact base string. An earlier pass using loose
# substring matching reported 53 place-name ARCs instead of 14, because the
# German "ort" matches inside "detector type", "reporter" and "vortexing";
# "row" matches "growth"; "location" matches "Memory allocation"; and "site"
# matches "Cloning Site". A loose match silently attaches wrong geography to
# real research data.
_PLACE_DENY = frozenset({
    "detector type", "reporter", "vortexing", "vortex mixer", "master resort",
    "suppressor type", "sample state", "biosource material state",
    "bioreactor type", "sensor type", "replacement solution component",
    "species_short_names", "accession_short_names",
    "short day length exposure", "temperature short day",
    "dataset ftp location", "data location", "memory allocation",
    "cloning site", "restriction sites", "restriction digestion site",
    "insertion site", "infiltration site", "coding region",
})

_WORD = re.compile(r"[a-z0-9_áéíóúñ]+")

# Precomputed token sets for the token-subset deny test in is_place_header.
_PLACE_DENY_TOKENS = frozenset(frozenset(_WORD.findall(term)) for term in _PLACE_DENY)


def unwrap_header(header: str) -> str:
    """'Parameter [longitude]' -> 'longitude'. Unwrapped headers pass through."""
    match = _WRAPPER.match(header)
    return (match.group("core") if match else header).strip()


def is_structural_header(header: str) -> bool:
    """True for Term Source REF / Term Accession Number / Unit columns."""
    return bool(_NON_HEADER.match(header))


def axis_of(core: str) -> str | None:
    """Return 'lat', 'lon', or None for an unwrapped header term."""
    text = core.lower()
    # "coordinates uncertainty" is a distance in metres, not an axis. Reject it
    # before the lat/lon test so a 222000 value never reaches a bbox.
    if "uncertaint" in text:
        return None
    if re.search(r"\blat(itude|itud)?\b", text) or "(latitude)" in text:
        return "lat"
    if re.search(r"\blon(gitude|gitud)?\b|\blng\b", text) or "(longitude)" in text:
        return "lon"
    return None


def role_from_header(core: str) -> str | None:
    """Return the role a header declares, or None for an ad-hoc header."""
    text = core.lower().strip()
    for prefix, role in _ROLE_BY_HEADER_PREFIX:
        if text.startswith(prefix):
            return role
    return None


def is_place_header(core: str) -> bool:
    """True when a header names a place. Word-boundary matched, deny list first."""
    text = core.lower().strip()
    tokens = set(_WORD.findall(text))
    if any(deny_tokens <= tokens for deny_tokens in _PLACE_DENY_TOKENS):
        return False
    if axis_of(core) is not None:
        return False
    if any(phrase in text for phrase in _PLACE_PHRASES):
        return True
    return bool(tokens & _PLACE_WORDS)


# ---------------------------------------------------------------------------
# Grouping
#
# Grouping keys on the COORDINATE, never on a label column. Measured on
# Teosinte: POBL has 3604 distinct values across 3604 rows (row-unique),
# ACCESION has 276, POB has 74, and there are 276 distinct coordinate pairs.
# Keying on POBL yields 3604 points instead of 276.
# ---------------------------------------------------------------------------

# Generic ISA identity columns: usable as a label, but only after any
# domain-specific column has been tried. Mapped to the bare field name
# because unwrap_header only strips Parameter/Characteristic/Factor/Comment/
# Component wrappers, not "Input [...]" - without this map, a generic-tier
# label_field would come back as the raw "Input [Source Name]" string while
# every specific-tier label_field is bare (e.g. "ACCESION"), and label_field
# is user-visible and exploded into a SQL view column by Task 11.
_GENERIC_LABEL_HEADERS = {
    "input [source name]": "Source Name",
    "input [sample name]": "Sample Name",
}


def points_from_tables(tables: list[Table], *, curated_role: str | None) -> list[dict]:
    """Return locations[] entries for every coordinate pair in `tables`.

    `curated_role` comes from harvester.geo_roles and applies only where a
    header declares no role of its own. A header-declared role always wins.
    """
    out: list[dict] = []
    for table in tables:
        out.extend(_points_from_table(table, curated_role=curated_role))
    out.sort(key=lambda p: (p["role"], p["point"]))
    return out


def _points_from_table(table: Table, *, curated_role: str | None) -> list[dict]:
    axes = _axis_columns(table)
    if not axes:
        return []

    entries: list[dict] = []
    for role, (lat_idx, lon_idx) in axes.items():
        groups: dict[tuple[float, float], list[int]] = {}
        lat_cells = table.columns[lat_idx]
        lon_cells = table.columns[lon_idx]
        for row in range(min(len(lat_cells), len(lon_cells))):
            lat = parse_coord(lat_cells[row], axis="lat")
            lon = parse_coord(lon_cells[row], axis="lon")
            if lat is None or lon is None:
                continue
            groups.setdefault((lon, lat), []).append(row)

        # Table-wide-constant rejection (in _label_candidates) only makes
        # sense when this role has more than one point to discriminate
        # between - see that function's docstring.
        labels = _label_candidates(table, many_groups=len(groups) > 1)

        for (lon, lat), rows in sorted(groups.items()):
            label, label_field = _label_for(table, labels, rows)
            entries.append({
                "role": role if role != "unspecified" else (curated_role or "unspecified"),
                "label": label,
                "label_field": label_field,
                "point": [lon, lat],
                "precision": "exact",
                "n_rows": len(rows),
                "source": table.source,
            })
    return entries


def _axis_columns(table: Table) -> dict[str, tuple[int, int]]:
    """Map each role present in `table` to its (lat index, lon index).

    Latitude and longitude are paired within one table only. Verified across
    the corpus: every ARC keeps both axes in the same sheet.

    The FIRST column for a given (role, axis) wins; a later duplicate (e.g.
    two `Parameter [latitude]` columns under the same role) is discarded with
    a warning rather than silently overwriting the first one's index.
    """
    by_role: dict[str, dict[str, int]] = {}
    for idx, header in enumerate(table.headers):
        if is_structural_header(header) or idx >= len(table.columns):
            continue
        core = unwrap_header(header)
        axis = axis_of(core)
        if axis is None:
            continue
        role = role_from_header(core) or "unspecified"
        role_axes = by_role.setdefault(role, {})
        if axis in role_axes:
            logger.warning(
                "Duplicate %s column for role %s in %s: keeping column %d, "
                "discarding column %d",
                axis,
                role,
                table.source,
                role_axes[axis],
                idx,
            )
            continue
        role_axes[axis] = idx
    return {
        role: (axes["lat"], axes["lon"])
        for role, axes in by_role.items()
        if "lat" in axes and "lon" in axes
    }


def _label_candidates(table: Table, *, many_groups: bool) -> list[tuple[int, str]]:
    """Candidate label columns, domain-specific ones before generic ISA ones.

    Row-unique columns are always rejected: the column's distinct non-blank
    value count equals the table's ROW count (not the non-blank cell count),
    so a per-row identifier is rejected without penalising a sparse-but-good
    column that happens to have all-distinct non-blank values. POBL is the
    motivating case: 3604 distinct values across 3604 rows.

    Table-wide-constant columns (every non-blank value identical across the
    whole table) are rejected only when `many_groups` is true - i.e. only
    when this role has more than one coordinate group to discriminate
    between. A constant column cannot discriminate between multiple points,
    so it is a bad label when there is more than one point; with exactly one
    point there is nothing to discriminate, and a constant column is the
    correct label, not a degenerate one (the common single-field-trial shape,
    where every good label column - ACCESION, SITE, Source Name - is
    constant across the table by construction). Teosinte's Parameter
    [Species] is the motivating case for the rejection: 2-3 values shared
    across all 3604 rows and constant within every one of its 276 sites, so
    left unchecked it would win as the label for every point ahead of
    ESTADO/ACCESION.
    """
    specific: list[tuple[int, str]] = []
    generic: list[tuple[int, str]] = []
    for idx, header in enumerate(table.headers):
        if is_structural_header(header) or idx >= len(table.columns):
            continue
        core = unwrap_header(header)
        if axis_of(core) is not None:
            continue
        column = table.columns[idx]
        cells = [c for c in column if c not in (None, "")]
        if not cells:
            continue
        if len(set(cells)) == len(column) and len(column) > 1:
            continue  # row-unique across the table: an identifier, not a label
        if many_groups and len(set(cells)) == 1 and len(cells) > 1:
            continue  # table-wide constant: cannot discriminate between points
        lowered = header.strip().lower()
        if lowered in _GENERIC_LABEL_HEADERS:
            generic.append((idx, _GENERIC_LABEL_HEADERS[lowered]))
        else:
            specific.append((idx, core))
    return specific + generic


def _label_for(
    table: Table, candidates: list[tuple[int, str]], rows: list[int]
) -> tuple[str | None, str | None]:
    """First candidate column that holds a single non-empty value across `rows`."""
    for idx, core in candidates:
        cells = table.columns[idx]
        values = {
            cells[r] for r in rows
            if r < len(cells) and cells[r] not in (None, "")
        }
        if len(values) == 1:
            return values.pop(), core
    return None, None


# ---------------------------------------------------------------------------
# Fallback resolution and precedence
#
# Precedence, first available wins: extracted, geocoded, institution, absent.
# A place name from the study's own data outranks an affiliation because it
# describes the material or site; an affiliation describes the custodian.
#
# locations[] always carries EVERY point from all tiers, so nothing is lost by
# the chain. Only geometry and location_status reflect the winning tier, which
# keeps the phase-2 Features collection complete even for a record whose
# geometry came from an institution.
# ---------------------------------------------------------------------------

_TIER_BY_ROLE = {
    "stated-place": "geocoded",
    "custodian-institution": "institution",
}
_TIER_ORDER = ("extracted", "geocoded", "institution")


def tier_of(role: str) -> str:
    """Which precedence tier a role belongs to."""
    return _TIER_BY_ROLE.get(role, "extracted")


def arc_path_from_uri(uri: str) -> str | None:
    """Extract a GitLab path_with_namespace from an ARC source URI.

    Returns None for a local file:// URI, which therefore never matches a
    curated override and correctly yields role "unspecified".
    """
    if not uri or not uri.startswith(("http://", "https://")):
        return None
    without_scheme = uri.split("://", 1)[1]
    if "/" not in without_scheme:
        return None
    path = without_scheme.split("/", 1)[1].strip("/")
    return path or None


def _place_points(tables) -> list[dict]:
    """Geocode place-name columns via the committed places table."""
    places = load_places()
    out: list[dict] = []
    seen: set[tuple[float, float]] = set()
    for table in tables:
        for idx, header in enumerate(table.headers):
            if is_structural_header(header) or idx >= len(table.columns):
                continue
            core = unwrap_header(header)
            if not is_place_header(core):
                continue
            counts: dict[str, int] = {}
            for cell in table.columns[idx]:
                if cell in (None, ""):
                    continue
                counts[str(cell).strip()] = counts.get(str(cell).strip(), 0) + 1
            for value, n_rows in sorted(counts.items()):
                entry = lookup(places, value)
                if entry is None:
                    continue
                point = [float(entry["point"][0]), float(entry["point"][1])]
                key = (point[0], point[1])
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "role": "stated-place",
                    "label": value,
                    "label_field": core,
                    "point": point,
                    "precision": entry.get("precision", "country"),
                    "n_rows": n_rows,
                    "source": table.source,
                })
    return out


def _institution_points(contacts) -> list[dict]:
    """Resolve author affiliations via the committed institutions table.

    Affiliation cells sometimes hold several institutions separated by ";";
    each part resolves independently and becomes its own point.
    """
    institutions = load_institutions()
    out: list[dict] = []
    seen: set[tuple[float, float]] = set()
    for contact in contacts:
        raw = getattr(contact, "affiliation", None)
        if not raw:
            continue
        for part in (p.strip() for p in str(raw).split(";")):
            if not part:
                continue
            entry = lookup(institutions, part)
            if entry is None:
                continue
            point = [float(entry["point"][0]), float(entry["point"][1])]
            key = (point[0], point[1])
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "role": "custodian-institution",
                "label": entry.get("name") or part,
                "label_field": "Investigation Person Affiliation",
                "point": point,
                "precision": entry.get("precision", "institution"),
                "n_rows": 1,
                "source": "affiliation",
            })
    return out


def resolve_locations(investigation, *, arc_source_uri: str) -> tuple[list[dict], str]:
    """Return (locations, location_status) for one Investigation."""
    arc_path = arc_path_from_uri(arc_source_uri)
    curated_role = role_for_arc(arc_path) if arc_path else None

    tables = list(getattr(investigation, "tables", None) or [])
    locations: list[dict] = []
    locations.extend(points_from_tables(tables, curated_role=curated_role))
    locations.extend(_place_points(tables))
    locations.extend(_institution_points(getattr(investigation, "contacts", None) or []))

    present = {tier_of(loc["role"]) for loc in locations}
    for tier in _TIER_ORDER:
        if tier in present:
            return locations, tier
    return locations, "absent"


def derive_geometry(locations: list[dict], status: str) -> dict | None:
    """Derive the record geometry from the winning tier's points.

    Point when every admitted point is identical, MultiPoint otherwise, null
    when there are none. NEVER a bbox Polygon: dormancy_NhuTran_2025 spans 259
    degrees of longitude, so a bbox would match nearly every spatial query
    while being confidently wrong, which is worse than absent.
    """
    if status == "absent":
        return None
    coords: list[list[float]] = []
    for loc in locations:
        if tier_of(loc["role"]) != status:
            continue
        point = [float(loc["point"][0]), float(loc["point"][1])]
        if point not in coords:
            coords.append(point)
    if not coords:
        return None
    coords.sort()
    if len(coords) == 1:
        return {"type": "Point", "coordinates": coords[0]}
    return {"type": "MultiPoint", "coordinates": coords}
