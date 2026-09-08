"""Project paths excluded from live enumeration on cost grounds.

Four ARCs in the DataPLANT corpus are pathologically expensive to parse.
`usadellab/BreedingValue-Public-Dataset` was measured at ~7h40m for a single
successful parse on the production VM (2026-08-31); the other three tripped a
300s `--parse-timeout` in the 2026-07-29 full-corpus dry run, in which every
other ARC of 209 finished under it. Root cause is `FsSpreadsheet.RescanRows`
walking every row through Fable's transpiled seq enumerator, so cost scales
with row count and grows faster than assay count.

Left in the nightly they cost roughly 30 hours of parse against a corpus that
otherwise finishes in about an hour. Seven consecutive nightly runs, 2026-09-01
to 2026-09-07, were killed by systemd's outer timeout without ever publishing.

This REVERSES the 2026-07-29 ruling that mega-ARCs get ingested with no time
limit because they are high-value phenotyping data. They are out of scope for
what INTERPLANT exposes, and the cost is not worth paying. Do not re-add one
without a fresh measurement.

Separate from harvester/filters.py because the two run at different stages
against different inputs: this matches GitLab project paths before anything is
cloned, filters.py inspects an already-parsed investigation. Enumeration is the
only stage where excluding helps at all.

Matching is exact, never fuzzy, for the same reason filters.py keeps its
placeholder list literal: a heuristic here would silently drop real research
data. `harvester ingest` and `harvester harvest --local-dir` bypass live
enumeration entirely, so any of these can still be ingested by hand on demand.
"""
from __future__ import annotations

# Exact `path_with_namespace` values, as GitLab reports them.
COST_EXCLUDED_PATHS = frozenset({
    "usadellab/BreedingValue-Public-Dataset",
    "lange/Curated_wheat_historical_phenotypic_data_from_European_Genebanks",
    "arendd/Historical_Phenomics_Wheat_Collection_IPK",
    "torsten.stoeter/rat-mri-ls",
})


def is_cost_excluded(path: str) -> bool:
    """True when `path` is one of the cost-excluded project paths."""
    return path in COST_EXCLUDED_PATHS
