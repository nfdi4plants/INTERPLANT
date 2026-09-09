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
