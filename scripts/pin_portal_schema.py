"""Fetch the Earth Data Portal's DocumentSchema.json and pin it locally.

Run this only when the upstream schema changes; the committed copy is what CI validates against.

Author: Mohamed Abouzid m.abouzid@fz-juelich.de
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

URL = "https://gitlab.awi.de/software-engineering/index/de.awi.index/-/raw/master/DocumentSchema.json"
DEST = Path(__file__).parent.parent / "docs" / "specs" / "schemas" / "portal-document-schema.json"


def main() -> int:
    with urllib.request.urlopen(URL) as resp:
        raw = resp.read()
    data = json.loads(raw)
    DEST.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"Pinned to {DEST} ({len(raw)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
