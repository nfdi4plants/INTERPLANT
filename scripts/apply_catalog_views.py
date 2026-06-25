"""Apply the catalog serving views to a Postgres DB.

Usage: python scripts/apply_catalog_views.py [DSN]
Defaults to the local-stack DSN when no argument is given.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harvester import db  # noqa: E402

_DEFAULT_DSN = "postgresql://interplant:interplant@localhost:5432/interplant"


def main() -> int:
    dsn = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_DSN
    conn = db.connect(dsn)
    db.apply_catalog_views(conn)
    print("catalog views applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
