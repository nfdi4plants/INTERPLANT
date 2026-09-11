"""Live verification of location extraction against real ARCs.

Gated: requires INTERPLANT_LIVE_HARVEST=1 and network access.
Run with: INTERPLANT_LIVE_HARVEST=1 uv run pytest tests/harvester/test_location_live.py -v
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from harvester.extractors.location import resolve_locations
from harvester.isa_reader import IsaReader

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("INTERPLANT_LIVE_HARVEST") != "1",
        reason="set INTERPLANT_LIVE_HARVEST=1 to run live ARC clones",
    ),
]

GITLAB = "https://git.nfdi4plants.org"


_SPARSE_PATTERNS = (
    "/isa.investigation.xlsx",
    "/studies/**/isa.study.xlsx",
    "/assays/**/isa.assay.xlsx",
)


def _clone(arc_path: str, dest: Path) -> None:
    """Clone only the ISA metadata sheets, never the raw data.

    resolve_locations reads nothing but the ISA spreadsheets
    (isa.investigation.xlsx, studies/*/isa.study.xlsx,
    assays/*/isa.assay.xlsx); the data blobs a full clone would fetch - raw
    reads, images, LFS artifacts - are never touched by the parser. A
    --filter=blob:none partial clone defers every blob, and the sparse
    checkout then requests only the sheets, so Teosinte (~2 GB of data)
    clones in seconds instead of minutes. Nothing needed by the extractor is
    lost: verified by parsing the sparse clone of shape/shape end to end.
    """
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}
    subprocess.run(
        [
            "git", "clone", "--depth", "1", "--filter=blob:none", "--no-checkout",
            f"{GITLAB}/{arc_path}.git", str(dest),
        ],
        check=True, capture_output=True, timeout=900, env=env,
    )
    subprocess.run(
        ["git", "sparse-checkout", "set", "--no-cone", *_SPARSE_PATTERNS],
        cwd=dest, check=True, capture_output=True, timeout=300, env=env,
    )
    subprocess.run(
        ["git", "checkout"],
        cwd=dest, check=True, capture_output=True, timeout=300, env=env,
    )


def _locations_for(arc_path: str) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "arc"
        _clone(arc_path, dest)
        investigation = IsaReader().read(dest)
        locations, _ = resolve_locations(
            investigation, arc_source_uri=f"{GITLAB}/{arc_path}"
        )
        return locations


def test_teosinte_yields_exactly_276_collection_sites() -> None:
    locations = _locations_for("usadellab/Teosinte")
    sites = [loc for loc in locations if loc["role"] == "collection-site"]
    assert len(sites) == 276
    # Mexico: lon about -107 to -87, lat about 12.9 to 26.2
    lons = [loc["point"][0] for loc in sites]
    lats = [loc["point"][1] for loc in sites]
    assert -107.0 < min(lons) and max(lons) < -86.0
    assert 12.0 < min(lats) and max(lats) < 27.0
    assert sum(loc["n_rows"] for loc in sites) == 3604


def test_flyover_coordinates_come_from_an_assay_table() -> None:
    locations = _locations_for("agdafair/flyover_redacted")
    sites = [loc for loc in locations if loc["role"] == "experiment-site"]
    assert len(sites) == 1
    assert sites[0]["source"].startswith("assays/")
    # Pins the cross-table merge sum (measured 2026-09-10): flyover_2025_01
    # (245 rows) + flyover_2025_02 (1108 rows). len(sites) == 1 alone would
    # still pass if the merge DROPPED an entry instead of summing it.
    assert sites[0]["n_rows"] == 1353


def test_quinoa_dms_values_parse() -> None:
    # 70 deg 47 min W, 28 deg 34 min S. A naive float() would put this in China.
    locations = _locations_for("usadellab/quinoa_chileanfieldtrial")
    sites = [loc for loc in locations if loc["role"] == "experiment-site"]
    # Pins the swap-corrected point measured 2026-09-10: exactly one site,
    # parsed exactly (not merely within range by coincidence of a degraded
    # precision).
    assert len(sites) == 1
    assert sites[0]["precision"] == "exact"
    lon, lat = sites[0]["point"]
    assert -71.0 < lon < -70.0
    assert -29.0 < lat < -28.0


def test_shape_carries_two_distinct_roles() -> None:
    locations = _locations_for("shape/shape")
    roles = {loc["role"] for loc in locations}
    assert {"material-origin", "material-source"} <= roles