"""Curated location roles for ARCs whose coordinate headers declare none.

Seven ARCs in the corpus carry bare `latitude`/`longitude` headers. No
automatic signal distinguishes a germplasm origin from an experiment site, as
measured on 2026-09-09:

- usadellab/Cassava_genome_sequencing_2017 has ONE point (Thailand) and it is
  provenance, while imetzen1/Methodfungalhyphae has ONE point (Cologne) and it
  is an experiment site. Point count does not discriminate.
- tntranloc/dormancy_NhuTran_2025 keeps 387 points in an assays/ file, but they
  are seed-accession origins spanning 259 degrees of longitude. File location
  does not discriminate.
- Both DAP_Seq and MARS pair a coordinate with a sample collection date, but so
  does Teosinte (FECHA, Fecha_de_siembra), which is provenance. Co-occurrence
  does not discriminate.

What actually separates the groups is whether the organism is a
researcher-grown lab line or crop, versus wild-collected germplasm - semantic
knowledge no header carries. So this map is hand-maintained and read once per
ARC by a human.

Matching is EXACT, never fuzzy, for the same reason harvester/exclusions.py
keeps its list literal: a heuristic here would silently attach wrong geography
to real research data.

Only "experiment-site" and "collection-site" may appear here. The
MIAPPE-specific "material-origin" and "material-source" are assigned only from
their literal headers, so a curated role can never imply a MIAPPE field the ARC
does not contain.

An ARC absent from this map gets role "unspecified". That is a correct,
queryable answer, not a gap to be filled by guessing.
"""
from __future__ import annotations

# Exact `path_with_namespace` values, as GitLab reports them.
GEO_ROLE_OVERRIDES: dict[str, str] = {
    # Wild teosinte subspecies: 276 accession sites across Mexico, with
    # ESTADO/PAIS columns naming Mexican states. Germplasm origins.
    "usadellab/Teosinte": "collection-site",
    # 387 seed-accession origins spanning 259 degrees of longitude, recorded in
    # the heat-treatment assay tables rather than a study table.
    "tntranloc/dormancy_NhuTran_2025": "collection-site",
    # One Thai coordinate (12.73 N, 101.14 E): the origin of the sequenced
    # cassava accession, not where sequencing happened.
    "usadellab/Cassava_genome_sequencing_2017": "collection-site",
    # Drone imagery captured over a single German field, in
    # assays/drone_image_capture.
    "agdafair/flyover_redacted": "experiment-site",
    # studies/FieldExperiment* at 50.93 N, 6.94 E (Cologne).
    "imetzen1/Methodfungalhyphae": "experiment-site",
    # Col-0 lab accession, greenhouse-grown for 4 weeks, sampled 2024-02-22.
    # The coordinate (52.04 N, 8.49 E, Bielefeld) is the greenhouse. Col-0 has
    # no meaningful provenance.
    "frommer/DAP_Seq": "experiment-site",
    # Zea mays grown in soil, flag leaf taken at flowering, sampled 2022-08-23
    # at 50.55 N, 6.21 E (Eifel). A growing site the authors harvested from.
    "x.zhou/MARS_ENA-Metabolights": "experiment-site",
}


def role_for_arc(arc_path: str) -> str | None:
    """Return the curated role for `arc_path`, or None when unlisted."""
    return GEO_ROLE_OVERRIDES.get(arc_path)
