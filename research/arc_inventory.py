#!/usr/bin/env python3
"""
arc_inventory.py - Harvest public DataPLANT ARCs from git.nfdi4plants.org via GitLab REST API.

Outputs:
  arc_inventory.jsonl      - one JSON object per ARC (incremental, crash-safe)
  arc_inventory_summary.json - aggregated domain counts

Usage:
  python arc_inventory.py                    # full run
  python arc_inventory.py --limit 10         # smoke test with first 10 projects
  python arc_inventory.py --output my.jsonl  # custom output path
  python arc_inventory.py --resume           # skip already-processed project IDs
  python arc_inventory.py --summarize-only   # rebuild summary from existing JSONL (no fetch)

Author: Mohamed Abouzid m.abouzid@fz-juelich.de
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://git.nfdi4plants.org/api/v4"

# Exact (lowercased) name → canonical domain
DOMAIN_MAP = {
    # Transcriptomics
    "rnaseq": "Transcriptomics",
    "rna-seq": "Transcriptomics",
    "rna_seq": "Transcriptomics",
    "mrnaseq": "Transcriptomics",
    "transcriptomics": "Transcriptomics",
    "scrnaseq": "Transcriptomics",
    "snrnaseq": "Transcriptomics",
    "singlecelltranscriptomics": "Transcriptomics",
    "single-cell transcriptomics": "Transcriptomics",
    "single_cell_transcriptomics": "Transcriptomics",
    "cold_transcriptomics_data": "Transcriptomics",
    "differentialexpressionanalysis": "Transcriptomics",
    "bsa_rnaseq": "Transcriptomics",
    # Proteomics
    "proteomics": "Proteomics",
    "gelbasedproteomics": "Proteomics",
    "ms": "Proteomics",
    "mseval": "Proteomics",
    "turboidassay": "Proteomics",
    "blotting": "Proteomics",
    "complexomics": "Proteomics",
    "mass spec assay": "Proteomics",
    "redoxnetworktopologyproteomics": "Proteomics",
    # Metabolomics
    "metabolomics": "Metabolomics",
    "gcqtof_targets": "Metabolomics",
    "masshunter_targets": "Metabolomics",
    "gcms": "Metabolomics",
    "gc-ms": "Metabolomics",
    "gc_ms": "Metabolomics",
    "lcms": "Metabolomics",
    "lc-ms": "Metabolomics",
    "lc_ms": "Metabolomics",
    "hplc": "Metabolomics",
    "nmr": "Metabolomics",
    "lipidomics": "Metabolomics",
    # Genomics
    "sequencing": "Genomics",
    "wgs": "Genomics",
    "dna-seq": "Genomics",
    "bsa_wgs": "Genomics",
    "chipseq": "Genomics",
    "chip-seq": "Genomics",
    "chip_seq": "Genomics",
    "chap-seq": "Genomics",
    "chapseq": "Genomics",
    "dapseq": "Genomics",
    "dap-seq": "Genomics",
    "atacseq": "Genomics",
    "atac-seq": "Genomics",
    "hi-c": "Genomics",
    "hic": "Genomics",
    # Imaging
    "microscopy": "Imaging",
    # Phenotyping
    "phenotyping": "Phenotyping",
    "growth": "Phenotyping",
    "growth_tests": "Phenotyping",
    "growth tests": "Phenotyping",
    "phenotypic_analysis": "Phenotyping",
    "phenotypic analysis": "Phenotyping",
    "barleyphenotyping": "Phenotyping",
    # QC (tag but don't count as a domain)
    "nanodrop": "QC",
    "bioanalyzer": "QC",
    "fragmentanalyzer": "QC",
    "qpcr": "QC",
}


# Ordered list of (substring, domain) for substring matching.
# Earlier entries win - put more specific terms first.
_SUBSTRING_RULES: list[tuple[str, str]] = [
    # QC first (most specific, must not be confused with domain assays)
    ("nanodrop", "QC"),
    ("bioanalyzer", "QC"),
    ("fragmentanalyzer", "QC"),
    ("fragment analyzer", "QC"),
    ("fastqc", "QC"),
    # Transcriptomics
    ("transcriptom", "Transcriptomics"),
    ("rnaseq", "Transcriptomics"),
    ("rna-seq", "Transcriptomics"),
    ("rna_seq", "Transcriptomics"),
    ("mrna", "Transcriptomics"),
    ("scrna", "Transcriptomics"),
    ("snrna", "Transcriptomics"),
    ("iso-seq", "Transcriptomics"),
    ("isoseq", "Transcriptomics"),
    ("single-cell rna", "Transcriptomics"),
    ("singlecell rna", "Transcriptomics"),
    # Proteomics
    ("proteom", "Proteomics"),
    ("mass spec", "Proteomics"),
    ("massspec", "Proteomics"),
    ("ms_data", "Proteomics"),
    ("western blot", "Proteomics"),
    ("immunoblot", "Proteomics"),
    ("sds-page", "Proteomics"),
    ("sdspage", "Proteomics"),
    ("co-ip", "Proteomics"),
    ("coip", "Proteomics"),
    ("complexom", "Proteomics"),
    ("turboid", "Proteomics"),
    # Metabolomics
    ("metabol", "Metabolomics"),
    ("gcms", "Metabolomics"),
    ("gc-ms", "Metabolomics"),
    ("gc_ms", "Metabolomics"),
    ("lcms", "Metabolomics"),
    ("lc-ms", "Metabolomics"),
    ("lc_ms", "Metabolomics"),
    ("lctof", "Metabolomics"),
    ("gctof", "Metabolomics"),
    ("hplc", "Metabolomics"),
    ("lipidom", "Metabolomics"),
    ("lipid profil", "Metabolomics"),
    ("nmr", "Metabolomics"),
    ("betalain", "Metabolomics"),
    ("flavonoid", "Metabolomics"),
    ("phenolic", "Metabolomics"),
    ("amino acid", "Metabolomics"),
    ("aminoacid", "Metabolomics"),
    ("carbohydrate", "Metabolomics"),
    ("squalene", "Metabolomics"),
    ("terpene", "Metabolomics"),
    ("sterol", "Metabolomics"),
    ("fame", "Metabolomics"),          # fatty acid methyl ester
    ("masshunter", "Metabolomics"),
    # Genomics
    ("sequencing", "Genomics"),
    ("genome assembl", "Genomics"),
    ("genome_assembl", "Genomics"),
    ("genome annot", "Genomics"),
    ("genome_annot", "Genomics"),
    ("chip-seq", "Genomics"),
    ("chipseq", "Genomics"),
    ("chap-seq", "Genomics"),
    ("chapseq", "Genomics"),
    ("dap-seq", "Genomics"),
    ("dapseq", "Genomics"),
    ("atac-seq", "Genomics"),
    ("atacseq", "Genomics"),
    ("hi-c", "Genomics"),
    ("snp array", "Genomics"),
    ("snp_array", "Genomics"),
    ("ont sequenc", "Genomics"),
    ("illumina sequenc", "Genomics"),
    ("wgs", "Genomics"),
    ("dna-seq", "Genomics"),
    ("bsa_wgs", "Genomics"),
    # Microbiome
    ("microbiota", "Microbiome"),
    ("microbiome", "Microbiome"),
    ("metabarcod", "Microbiome"),
    ("amplicon seq", "Microbiome"),
    ("16s_", "Microbiome"),
    ("_16s", "Microbiome"),
    ("18s_euk", "Microbiome"),
    ("18s_raw", "Microbiome"),
    ("metagenom", "Microbiome"),
    ("community profil", "Microbiome"),
    # Phenotyping
    ("phenotyp", "Phenotyping"),
    ("morpholog", "Phenotyping"),
    ("biomass", "Phenotyping"),
    ("flowering", "Phenotyping"),
    ("germination", "Phenotyping"),
    ("growth monitor", "Phenotyping"),
    ("growth_monitor", "Phenotyping"),
    ("root length", "Phenotyping"),
    ("shoot weight", "Phenotyping"),
    ("shoot fresh", "Phenotyping"),
    ("leaf area", "Phenotyping"),
    ("plant height", "Phenotyping"),
    ("yield", "Phenotyping"),
    ("growth", "Phenotyping"),
    # Imaging
    ("microscop", "Imaging"),
    ("fluorescen", "Imaging"),
    ("confocal", "Imaging"),
    ("drone imag", "Imaging"),
    ("ct scan", "Imaging"),
    ("electron micro", "Imaging"),
    # QC (additional)
    ("dna extraction", "QC"),
    ("dna isolation", "QC"),
    ("dna_extraction", "QC"),
    ("dna_isolation", "QC"),
    ("rna extraction", "QC"),
    ("rna_extraction", "QC"),
    ("quality control", "QC"),
    ("quality_control", "QC"),
    ("read_quality", "QC"),
    ("readquality", "QC"),
    ("qpcr", "QC"),
    ("cpcr", "QC"),
    ("trimming", "QC"),
    ("trimmomatic", "QC"),
    ("fastq", "QC"),
    # Transcriptomics (additional)
    ("deg", "Transcriptomics"),          # differentially expressed genes
    ("differentialexpression", "Transcriptomics"),
    ("go_term", "Transcriptomics"),
    ("go term", "Transcriptomics"),
    ("goenrich", "Transcriptomics"),
    ("gene expression", "Transcriptomics"),
    ("gene_expression", "Transcriptomics"),
    ("expressionanalysis", "Transcriptomics"),
    ("expression_analysis", "Transcriptomics"),
    ("expression comparison", "Transcriptomics"),
    # Genomics (additional)
    ("variant_call", "Genomics"),
    ("variantcall", "Genomics"),
    ("genome", "Genomics"),
    ("dna hybridization", "Genomics"),
    ("dna_hybridization", "Genomics"),
    ("mapping population", "Genomics"),
    ("mapping_population", "Genomics"),
    ("biparental_mapping", "Genomics"),
    ("qtl", "Genomics"),
    ("snp", "Genomics"),
    ("amplicon", "Genomics"),            # dna amplicon (not metabarcoding)
    ("library preparation", "Genomics"),
    ("library_preparation", "Genomics"),
    ("crispr", "Genomics"),
    ("mutagenesis", "Genomics"),
    ("mutagene", "Genomics"),
    # Phenotyping (additional)
    ("seed_germination", "Phenotyping"),
    ("seedling", "Phenotyping"),
    ("germination", "Phenotyping"),
    ("nematode", "Phenotyping"),         # plant-nematode interaction assays
    ("infection assay", "Phenotyping"),
    ("infection_assay", "Phenotyping"),
    ("colonization", "Phenotyping"),
    ("root exudat", "Phenotyping"),
    ("plant growth", "Phenotyping"),
    ("plant_growth", "Phenotyping"),
    ("plant resistance", "Phenotyping"),
    ("shoot fresh", "Phenotyping"),
    ("shoot_fresh", "Phenotyping"),
    ("fresh mass", "Phenotyping"),
    ("fresh_mass", "Phenotyping"),
    ("dry_weight", "Phenotyping"),
    ("dry weight", "Phenotyping"),
    ("plant_height", "Phenotyping"),
    ("cell_viability", "Phenotyping"),
    ("cell viability", "Phenotyping"),
    ("flowering_time", "Phenotyping"),
    ("plant_architecture", "Phenotyping"),
    ("pollen_viability", "Phenotyping"),
    ("leaf_development", "Phenotyping"),
    ("grain_size", "Phenotyping"),
    ("sugar_measurement", "Phenotyping"),
    # Metabolomics (additional)
    ("pigment", "Metabolomics"),
    ("chlorophyll", "Metabolomics"),     # pigment quantification
    ("secondary metabol", "Metabolomics"),
    ("volatile", "Metabolomics"),
    ("alkaloid", "Metabolomics"),
    ("glucosino", "Metabolomics"),
    ("ethanol_production", "Metabolomics"),
    ("free_amino_acid", "Metabolomics"),
    ("free amino acid", "Metabolomics"),
    ("carbohydrate_quantif", "Metabolomics"),
    ("carbon_and_nitrogen", "Metabolomics"),
    ("elemental_analysis", "Metabolomics"),
    ("element analysis", "Metabolomics"),
    ("enzyme activity", "Metabolomics"),
    ("enzyme_activity", "Metabolomics"),
    # Microbiome (additional)
    ("community profiling", "Microbiome"),
    ("community_profiling", "Microbiome"),
    ("microbial", "Microbiome"),
    ("microbiota", "Microbiome"),
    ("16s", "Microbiome"),
    ("18s", "Microbiome"),
    ("its_sequencing", "Microbiome"),
    ("its sequencing", "Microbiome"),
    # Imaging (additional)
    ("spinning disk", "Imaging"),
    ("spinningdisk", "Imaging"),
    ("lightsheet", "Imaging"),
    ("light sheet", "Imaging"),
    ("light_sheet", "Imaging"),
    ("mri", "Imaging"),
    ("ir imaging", "Imaging"),
    ("irimaging", "Imaging"),
    ("white light imaging", "Imaging"),
    ("whitelightimaging", "Imaging"),
    ("molecular cartography", "Imaging"),
    ("molecularcartography", "Imaging"),
    ("backscatter", "Imaging"),
    ("microfluidic", "Imaging"),
    ("histochemical", "Imaging"),
    ("staining", "Imaging"),
    ("gus histochem", "Imaging"),
    ("protein localization", "Imaging"),
    ("protein_localization", "Imaging"),
    ("fluorescein", "Imaging"),
    ("drone", "Imaging"),
    # Genomics (additional)
    ("gwas", "Genomics"),
    ("assembly qc", "Genomics"),
    ("assembly_qc", "Genomics"),
    ("peak calling", "Genomics"),
    ("peakcalling", "Genomics"),
    ("peak_calling", "Genomics"),
    ("assembly", "Genomics"),
    ("annotation", "Genomics"),
    ("msa", "Genomics"),               # multiple sequence alignment
    ("homolog", "Genomics"),
    ("bombardment", "Genomics"),       # biolistic transformation
    ("cna", "Genomics"),               # copy number analysis
    ("quasi_mapping", "Transcriptomics"),  # Salmon/Kallisto RNA-seq
    ("quasimapping", "Transcriptomics"),
    ("microarray", "Transcriptomics"),
    ("porechop", "QC"),                # ONT read trimming
    ("mapping_population", "Genomics"),
    # Proteomics (additional)
    ("chlrecurtip", "Proteomics"),     # chloroplast IP+MS experiments
    ("protein production", "Proteomics"),
    ("protein_production", "Proteomics"),
    ("protein purification", "Proteomics"),
    ("protein_purification", "Proteomics"),
    ("expression_and_purification", "Proteomics"),
    ("expression and purification", "Proteomics"),
    ("protstab", "Proteomics"),        # protein stability datasets
    ("complextab", "Proteomics"),
    ("complex_tab", "Proteomics"),
    # Phenotyping (additional)
    ("icarda", "Phenotyping"),         # ICARDA field trial stations
    ("crea_", "Phenotyping"),          # Italian field research stations
    ("phenology", "Phenotyping"),
    ("relative_water_content", "Phenotyping"),
    ("relative water content", "Phenotyping"),
    ("weather_data", "Phenotyping"),
    ("weather data", "Phenotyping"),
    ("observation_unit", "Phenotyping"),  # MIAPPE observation unit data
    ("observation unit", "Phenotyping"),
    ("plant_height_measurement", "Phenotyping"),
    ("plant height measurement", "Phenotyping"),
    ("biolector", "Phenotyping"),      # biomass monitoring bioreactor
    ("spring_202", "Phenotyping"),     # seasonal field trials
    ("winter_202", "Phenotyping"),
    ("co-cultivation", "Phenotyping"),
    ("co_cultivation", "Phenotyping"),
    ("inoculation", "Phenotyping"),
    ("infection", "Phenotyping"),
    ("confrontation", "Phenotyping"),
    ("dcw", "Phenotyping"),            # dry cell weight
    ("miniPam", "Phenotyping"),        # photosynthesis fluorometer
    ("minipam", "Phenotyping"),
    # Metabolomics (additional)
    ("qtof", "Metabolomics"),          # catches GCqTOF, LCqTOF
    ("cellulose", "Metabolomics"),
    ("carbon_and_nitrogen", "Metabolomics"),
    ("carbonandnitrogen", "Metabolomics"),
    ("element", "Metabolomics"),       # elemental analysis
    ("flux_balance", "Metabolomics"),  # metabolic flux
    ("fluxbalance", "Metabolomics"),
    # Phenotyping (additional)
    ("plantheight", "Phenotyping"),    # PlantHeightMeasurement (camelCase)
    ("a_spring", "Phenotyping"),       # a_spring_wheat historical trials
    ("a_winter", "Phenotyping"),       # a_winter_wheat historical trials
    ("a_weather", "Phenotyping"),
    ("with-observation", "Phenotyping"),  # MIAPPE with/without observation units
    ("without-observation", "Phenotyping"),
    ("jhi-barley", "Phenotyping"),
    ("jhi-blueberry", "Phenotyping"),
    ("jhi-test", "Phenotyping"),
    # Imaging (additional)
    ("flow cytometry", "Imaging"),
    ("flow_cytometry", "Imaging"),
    ("particle counter", "Imaging"),
    ("particle_counter", "Imaging"),
    # Proteomics (additional)
    ("chloroplas", "Proteomics"),      # chloroplast enrichment/isolation (incl. typos)
    ("cold_chloro", "Proteomics"),
    # QC (additional)
    ("dilutionseries", "QC"),
    ("dilution_series", "QC"),
    ("dilution series", "QC"),
    ("test_ms", "Proteomics"),         # test MS assay → Proteomics
    # Proteomics (additional)
    ("sasacomputation", "Proteomics"),  # solvent accessible surface area
    ("sasa", "Proteomics"),
    # Microbiome (additional)
    ("phage", "Microbiome"),
    ("streptomyces", "Microbiome"),
    ("bacteriophage", "Microbiome"),
]


_PREFIX_RE = re.compile(
    r"^(?:[a-z]?\d+[_\-])+",  # strip 01_, G01_, A1_, 1-2_, 2_7- etc.
    re.IGNORECASE,
)


def normalize(name: str) -> str:
    key = name.lower().strip()

    # Prefix-based exact matches first
    if key.startswith("clsm"):
        return "Imaging"

    # Direct lookup in exact map
    exact = DOMAIN_MAP.get(key)
    if exact:
        return exact

    # Substring matching on original key (ordered - first match wins)
    for substr, domain in _SUBSTRING_RULES:
        if substr in key:
            return domain

    # Strip common numbered prefixes (01_, G01_, A1_, 1-2_, …) and retry
    stripped = _PREFIX_RE.sub("", key).strip()
    if stripped and stripped != key:
        exact2 = DOMAIN_MAP.get(stripped)
        if exact2:
            return exact2
        for substr, domain in _SUBSTRING_RULES:
            if substr in stripped:
                return domain

    return "Unclassified"


def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": "INTERPLANT-inventory/0.1"})
    return s


def get_json(session: requests.Session, url: str, params: dict = None) -> tuple:
    """Returns (data, response) or raises on error."""
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json(), resp


def fetch_all_projects(session: requests.Session, limit: int = None) -> list:
    """Enumerate all public non-archived projects with pagination."""
    projects = []
    page = 1
    total_pages = None

    while True:
        params = {"visibility": "public", "per_page": 100, "page": page}
        data, resp = get_json(session, f"{BASE_URL}/projects", params)

        if total_pages is None:
            total_pages = int(resp.headers.get("x-total-pages", 1))
            print(f"  Total pages: {total_pages}", flush=True)

        for proj in data:
            if proj.get("archived"):
                continue
            projects.append(proj)
            if limit and len(projects) >= limit:
                print(f"  --limit {limit} reached, stopping project fetch.", flush=True)
                return projects

        print(f"  Page {page}/{total_pages} - {len(projects)} projects so far", flush=True)

        if page >= total_pages:
            break
        page += 1
        time.sleep(0.2)

    return projects


def get_root_tree(session: requests.Session, project_id: int, branch: str) -> list:
    """Return list of root-level tree entries."""
    try:
        data, _ = get_json(
            session,
            f"{BASE_URL}/projects/{project_id}/repository/tree",
            {"ref": branch, "per_page": 100},
        )
        return data
    except requests.HTTPError as e:
        if e.response.status_code in (404, 500):
            return []
        raise


def get_subfolder_names(session: requests.Session, project_id: int, branch: str, path: str) -> list:
    """Return list of folder names directly under `path`."""
    try:
        data, _ = get_json(
            session,
            f"{BASE_URL}/projects/{project_id}/repository/tree",
            {"path": path, "ref": branch, "per_page": 100},
        )
        return [entry["name"] for entry in data if entry.get("type") == "tree"]
    except requests.HTTPError as e:
        if e.response.status_code in (404, 500):
            return []
        raise


def is_arc(root_entries: list) -> bool:
    """An ARC must have isa.investigation.xlsx at the root."""
    names = {e["name"] for e in root_entries}
    return "isa.investigation.xlsx" in names


def process_project(session: requests.Session, proj: dict) -> dict | None:
    """
    Check if a project is an ARC and harvest its assay/study folders.
    Returns a record dict or None if not an ARC.
    """
    pid = proj["id"]
    branch = proj.get("default_branch") or "main"

    root_entries = get_root_tree(session, pid, branch)
    if not root_entries:
        return None

    if not is_arc(root_entries):
        return None

    assay_folders = get_subfolder_names(session, pid, branch, "assays")
    study_folders = get_subfolder_names(session, pid, branch, "studies")

    forked_from = proj.get("forked_from_project")
    record = {
        "id": pid,
        "name": proj["name"],
        "path_with_namespace": proj["path_with_namespace"],
        "description": proj.get("description"),
        "topics": proj.get("topics", []),
        "default_branch": branch,
        "web_url": proj["web_url"],
        "namespace": proj.get("namespace", {}).get("full_path"),
        "created_at": proj.get("created_at"),
        "last_activity_at": proj.get("last_activity_at"),
        "forks_count": proj.get("forks_count", 0),
        "star_count": proj.get("star_count", 0),
        "is_fork": forked_from is not None,
        "forked_from": (
            {
                "id": forked_from["id"],
                "name": forked_from["name"],
                "namespace": forked_from.get("namespace", {}).get("full_path"),
            }
            if forked_from
            else None
        ),
        "assay_folders": assay_folders,
        "study_folders": study_folders,
    }
    return record


def load_processed_ids(jsonl_path: Path) -> set:
    ids = set()
    if not jsonl_path.exists():
        return ids
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    ids.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return ids


def build_summary(jsonl_path: Path, total_projects, archived_skipped, not_arc_skipped) -> dict:
    arcs = []
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                arcs.append(json.loads(line))

    originals = [a for a in arcs if not a["is_fork"]]
    forks = [a for a in arcs if a["is_fork"]]

    raw_freq: dict[str, int] = {}
    for arc in arcs:
        for folder in arc["assay_folders"]:
            raw_freq[folder] = raw_freq.get(folder, 0) + 1

    top_raw = dict(sorted(raw_freq.items(), key=lambda x: -x[1])[:50])

    def domain_counts(arc_list: list) -> dict:
        counts: dict[str, int] = {}
        unclassified_names = set()
        for arc in arc_list:
            domains = set()
            for folder in arc["assay_folders"]:
                canonical = normalize(folder)
                if canonical == "QC":
                    continue
                if canonical == "Unclassified":
                    unclassified_names.add(folder)
                    continue
                domains.add(canonical)
            if len(domains) > 1:
                label = "Multi-omics"
            elif len(domains) == 1:
                label = next(iter(domains))
            else:
                label = "Unclassified"
            counts[label] = counts.get(label, 0) + 1
        return counts, sorted(unclassified_names)

    orig_counts, unclassified_names = domain_counts(originals)
    all_counts, _ = domain_counts(arcs)

    total_arcs = len(arcs)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_projects": total_projects,
        "total_arcs": total_arcs,
        "archived_skipped": archived_skipped,
        "not_arc_skipped": not_arc_skipped,
        "originals_count": len(originals),
        "forks_count": len(forks),
        "raw_assay_frequency": top_raw,
        "domain_counts_originals_only": orig_counts,
        "domain_counts_all_arcs": all_counts,
        "unclassified_raw_names": unclassified_names,
    }


def main():
    parser = argparse.ArgumentParser(description="Harvest DataPLANT ARC metadata via GitLab API")
    parser.add_argument("--limit", type=int, help="Stop after N projects (smoke test)")
    parser.add_argument("--output", default="arc_inventory.jsonl", help="Output JSONL path")
    parser.add_argument("--resume", action="store_true", help="Skip already-processed project IDs")
    parser.add_argument("--summarize-only", action="store_true",
                        help="Rebuild summary from existing JSONL without fetching again")
    args = parser.parse_args()

    out_path = Path(args.output)
    summary_path = out_path.with_suffix("").with_name(out_path.stem + "_summary.json")

    if args.summarize_only:
        if not out_path.exists():
            print(f"ERROR: {out_path} not found - run without --summarize-only first.", file=sys.stderr)
            sys.exit(1)
        existing = load_processed_ids(out_path)
        print(f"--summarize-only: rebuilding from {len(existing)} records in {out_path}", flush=True)
        summary = build_summary(out_path, total_projects=None, archived_skipped=None, not_arc_skipped=None)
        summary_path.write_text(json.dumps(summary, indent=2))
        print(f"Summary written to {summary_path}", flush=True)
        print(f"\n=== SUMMARY ===")
        print(f"Total ARCs: {summary['total_arcs']} ({summary['originals_count']} originals, {summary['forks_count']} forks)")
        print(f"Domain counts (originals only):")
        for domain, count in sorted(summary["domain_counts_originals_only"].items(), key=lambda x: -x[1]):
            print(f"  {domain:20s}: {count}")
        if summary["unclassified_raw_names"]:
            unc = summary["unclassified_raw_names"]
            print(f"\nUnclassified folder names ({len(unc)}):")
            for n in unc[:30]:
                print(f"  {n}")
        return

    session = make_session()

    already_done: set = set()
    if args.resume and out_path.exists():
        already_done = load_processed_ids(out_path)
        print(f"Resume mode: {len(already_done)} projects already in output.", flush=True)

    print("Fetching project list...", flush=True)
    projects = fetch_all_projects(session, limit=args.limit)
    total_projects = len(projects)
    print(f"  {total_projects} non-archived projects fetched.", flush=True)

    archived_skipped = 0
    not_arc_skipped = 0
    arc_count = 0

    mode = "a" if args.resume else "w"
    with out_path.open(mode) as f_out:
        for i, proj in enumerate(projects, 1):
            pid = proj["id"]
            name = proj.get("path_with_namespace", proj["name"])

            if pid in already_done:
                print(f"  [{i}/{total_projects}] SKIP (already done): {name}", flush=True)
                arc_count += 1
                continue

            print(f"  [{i}/{total_projects}] Checking: {name}", flush=True)

            try:
                record = process_project(session, proj)
            except Exception as e:
                print(f"    ERROR processing {name}: {e}", file=sys.stderr, flush=True)
                continue

            if record is None:
                not_arc_skipped += 1
                print(f"    → not an ARC", flush=True)
            else:
                arc_count += 1
                fork_tag = " [fork]" if record["is_fork"] else ""
                assays = record["assay_folders"]
                print(f"    → ARC{fork_tag}: assays={assays}", flush=True)
                f_out.write(json.dumps(record) + "\n")
                f_out.flush()

            time.sleep(0.1)

    print(f"\nDone. {arc_count} ARCs found, {not_arc_skipped} non-ARCs skipped.", flush=True)
    print(f"Building summary...", flush=True)

    summary = build_summary(out_path, total_projects, archived_skipped, not_arc_skipped)
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"Summary written to {summary_path}", flush=True)

    # Print key stats
    print(f"\n=== SUMMARY ===")
    print(f"Total ARCs:      {summary['total_arcs']} ({summary['originals_count']} originals, {summary['forks_count']} forks)")
    print(f"Domain counts (originals only):")
    for domain, count in sorted(summary["domain_counts_originals_only"].items(), key=lambda x: -x[1]):
        print(f"  {domain:20s}: {count}")
    if summary["unclassified_raw_names"]:
        print(f"\nUnclassified folder names ({len(summary['unclassified_raw_names'])}):")
        for name in summary["unclassified_raw_names"][:20]:
            print(f"  {name}")


if __name__ == "__main__":
    main()
