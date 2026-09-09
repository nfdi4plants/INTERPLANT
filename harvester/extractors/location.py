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

import re

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


def parse_coord(raw: object, *, axis: str) -> float | None:
    """Parse one cell into a signed decimal degree, or None if unusable.

    `axis` ("lat" or "lon") selects the range check. A trailing N/S/E/W sets
    the sign and overrides any leading sign, because "70°47′ W" is negative
    longitude and a naive float() would place it in the eastern hemisphere.
    """
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
    if hemi in ("S", "W"):
        value = -value
    elif hemi in ("N", "E"):
        pass
    elif match.group("sign") == "-":
        value = -value

    limit = _AXIS_LIMIT[axis]
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
_PLACE_WORDS = frozenset({
    "country", "pais", "país", "state", "estado", "province", "region",
    "locality", "city", "ciudad", "town", "village", "municipality",
    "county", "district", "standort", "geographic", "location", "area",
    "origin",
})

# Multi-word place phrases, substring-matched after the deny list.
_PLACE_PHRASES = (
    "geographic location", "geographic area", "experimental site name",
    "country code", "country_or_area", "collection site", "sampling site",
    "field site", "site name",
)

# Measured false positives. An earlier pass using loose substring matching
# reported 53 place-name ARCs instead of 14, because the German "ort" matches
# inside "detector type", "reporter" and "vortexing"; "row" matches "growth";
# "location" matches "Memory allocation"; and "site" matches "Cloning Site".
# A loose match silently attaches wrong geography to real research data.
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
    if text in _PLACE_DENY:
        return False
    if axis_of(core) is not None:
        return False
    if any(phrase in text for phrase in _PLACE_PHRASES):
        return True
    return bool(set(_WORD.findall(text)) & _PLACE_WORDS)
