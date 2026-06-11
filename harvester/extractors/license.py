"""Extract a license string from a parsed Investigation or a LICENSE file."""
from __future__ import annotations

from pathlib import Path

from harvester.isa_reader import Investigation

_LICENSE_FILENAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt")


def extract_license(investigation: Investigation, arc_root: Path) -> str | None:
    """Return a license string: investigation value first, else LICENSE file."""
    if investigation.license and investigation.license.strip():
        return investigation.license.strip()
    for name in _LICENSE_FILENAMES:
        candidate = arc_root / name
        if candidate.is_file():
            for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip():
                    return line.strip()
    return None
