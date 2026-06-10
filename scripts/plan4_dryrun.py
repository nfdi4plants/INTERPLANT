"""Plan 4 dry-run: diagnostic probe of the harvester pipeline against real public ARCs.

READ-ONLY - does not write to any database, does not commit anything, does not
modify any existing source file.  Creates only this script and the report at
docs/progress/2026-06-10-plan4-dryrun.md.

Pipeline stages tested per ARC:
  1. clone  - shallow git clone, LFS skipped
  2. parse  - IsaReader.read() via arctrl
  3. omics  - classify_omics() per assay folder
  4. build  - build_record()
  5. validate - Draft202012Validator against record.schema.json + assay-extensions

Run with:  uv run python scripts/plan4_dryrun.py
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
import traceback
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("plan4_dryrun")

# ---------------------------------------------------------------------------
# Repo-root / schema paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
SCHEMAS_DIR = REPO_ROOT / "docs" / "specs" / "schemas"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GITLAB_BASE = "https://git.nfdi4plants.org"
MAX_PAGES = 3
SAMPLE_SIZE = 20
FIXED_TS = "2026-06-10T00:00:00Z"
CLONE_TIMEOUT_S = 60

# ---------------------------------------------------------------------------
# Per-ARC result container
# ---------------------------------------------------------------------------

@dataclass
class ArcResult:
    # identity
    project_id: int = 0
    path: str = ""
    web_url: str = ""
    last_activity_at: str = ""

    # stage outcomes
    clone_ok: bool = False
    clone_error: str = ""

    parse_ok: bool = False
    parse_error: str = ""
    parse_exc_type: str = ""
    n_studies: int = 0
    n_assays: int = 0
    n_contacts: int = 0
    n_dois: int = 0
    n_assays_with_mtype: int = 0

    omics_classified: int = 0   # matched a real domain (not None)
    omics_total: int = 0        # total assay folders classified

    build_ok: bool = False
    build_error: str = ""

    validate_ok: bool = False
    validate_errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Schema validator construction (mirrors conftest.py logic)
# ---------------------------------------------------------------------------

def _make_validator():
    """Build a Draft202012Validator with the assay-extensions registry."""
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    record_schema = json.loads(
        (SCHEMAS_DIR / "record.schema.json").read_text(encoding="utf-8")
    )
    extensions_schema = json.loads(
        (SCHEMAS_DIR / "assay-extensions.schema.json").read_text(encoding="utf-8")
    )
    registry: Registry = Registry().with_resource(
        "https://interplant.org/schemas/assay-extensions.schema.json",
        Resource.from_contents(extensions_schema),
    )
    format_checker = Draft202012Validator.FORMAT_CHECKER
    return Draft202012Validator(
        record_schema,
        registry=registry,
        format_checker=format_checker,
    )


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------

def _clone_arc(web_url: str, tmpdir: Path) -> tuple[bool, str]:
    """Shallow-clone an ARC repo; skip LFS blobs.  Returns (ok, error_summary)."""
    clone_url = web_url.rstrip("/") + ".git"
    env = {"GIT_LFS_SKIP_SMUDGE": "1"}
    import os
    merged_env = {**os.environ, **env}
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(tmpdir)],
            capture_output=True,
            text=True,
            timeout=CLONE_TIMEOUT_S,
            env=merged_env,
        )
        if result.returncode != 0:
            summary = (result.stderr or result.stdout or "").strip()
            return False, summary[:200]
        return True, ""
    except subprocess.TimeoutExpired:
        return False, f"clone timed out after {CLONE_TIMEOUT_S}s"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def _parse_arc(arc_root: Path) -> tuple[Any, str, str]:
    """Run IsaReader.read(); returns (investigation_or_None, exc_type, error_msg)."""
    # Import here so a missing arctrl produces a clear error scoped to this stage.
    sys.path.insert(0, str(REPO_ROOT))
    from harvester.isa_reader import IsaReader
    try:
        investigation = IsaReader().read(arc_root)
        return investigation, "", ""
    except Exception as exc:  # noqa: BLE001
        return None, type(exc).__name__, str(exc)[:300]


def _classify_assays(investigation) -> tuple[dict[str, str], int, int]:
    """Run classify_omics on every assay folder.

    Returns (omics_by_folder, n_classified_non_none, n_total).
    """
    from harvester.classifiers.omics import classify_omics

    omics_by_folder: dict[str, str] = {}
    n_total = 0
    n_classified = 0
    seen: set[str] = set()
    for study in investigation.studies:
        for assay in study.assays:
            folder = assay.folder
            if folder in seen:
                continue
            seen.add(folder)
            n_total += 1
            domain = classify_omics(folder)
            omics_by_folder[folder] = domain or "other"
            if domain is not None:
                n_classified += 1
    return omics_by_folder, n_classified, n_total


def _build(investigation, omics_by_folder: dict[str, str], web_url: str) -> tuple[Any, str]:
    """Run build_record(); returns (record_or_None, error_msg)."""
    from harvester.build import build_record
    try:
        record = build_record(
            investigation,
            omics_by_folder,
            arc_source_uri=web_url,
            harvested_at=FIXED_TS,
            created=FIXED_TS,
            updated=FIXED_TS,
        )
        return record, ""
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def _validate(validator, record: dict) -> list[str]:
    """Return list of validation error strings (empty = valid)."""
    errors = []
    for err in validator.iter_errors(record):
        path = ".".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(f"{path}: {err.message[:200]}")
    return errors


# ---------------------------------------------------------------------------
# Main run loop
# ---------------------------------------------------------------------------

def run_dryrun() -> list[ArcResult]:
    sys.path.insert(0, str(REPO_ROOT))
    from harvester.enumerate import iter_public_arcs

    log.info("Building schema validator ...")
    validator = _make_validator()

    log.info("Enumerating public ARCs from %s (max_pages=%d) ...", GITLAB_BASE, MAX_PAGES)
    arcs_meta: list[dict] = []
    try:
        for meta in iter_public_arcs(GITLAB_BASE, max_pages=MAX_PAGES):
            arcs_meta.append(meta)
            if len(arcs_meta) >= SAMPLE_SIZE:
                break
    except Exception as exc:  # noqa: BLE001
        log.error("Enumeration failed: %s", exc)
        traceback.print_exc()
        return []

    log.info("Enumerated %d ARCs; processing up to %d ...", len(arcs_meta), SAMPLE_SIZE)

    results: list[ArcResult] = []

    for idx, meta in enumerate(arcs_meta, 1):
        r = ArcResult(
            project_id=meta["project_id"],
            path=meta["path_with_namespace"],
            web_url=meta["web_url"],
            last_activity_at=meta.get("last_activity_at", ""),
        )
        log.info("[%d/%d] %s", idx, len(arcs_meta), r.path)

        with tempfile.TemporaryDirectory(prefix="plan4_dryrun_") as tmpdir:
            arc_root = Path(tmpdir)

            # -- Stage 1: clone ------------------------------------------------
            clone_ok, clone_err = _clone_arc(r.web_url, arc_root)
            r.clone_ok = clone_ok
            r.clone_error = clone_err
            if not clone_ok:
                log.warning("  clone FAILED: %s", clone_err)
                results.append(r)
                continue
            log.info("  clone ok")

            # -- Stage 2: parse ------------------------------------------------
            investigation, exc_type, parse_err = _parse_arc(arc_root)
            r.parse_ok = investigation is not None
            r.parse_error = parse_err
            r.parse_exc_type = exc_type
            if not r.parse_ok:
                log.warning("  parse FAILED (%s): %s", exc_type, parse_err)
                results.append(r)
                continue

            r.n_studies = len(investigation.studies)
            r.n_contacts = len(investigation.contacts)
            r.n_dois = len(investigation.dois)
            assay_count = sum(len(s.assays) for s in investigation.studies)
            r.n_assays = assay_count
            r.n_assays_with_mtype = sum(
                1 for s in investigation.studies
                for a in s.assays if a.measurement_type is not None
            )
            log.info(
                "  parse ok - studies=%d assays=%d contacts=%d dois=%d mtype_set=%d",
                r.n_studies, r.n_assays, r.n_contacts, r.n_dois, r.n_assays_with_mtype,
            )

            # -- Stage 3: omics classification ---------------------------------
            omics_by_folder, n_classified, n_total = _classify_assays(investigation)
            r.omics_classified = n_classified
            r.omics_total = n_total
            log.info(
                "  omics - classified=%d/%d",
                n_classified, n_total,
            )

            # -- Stage 4: build ------------------------------------------------
            record, build_err = _build(investigation, omics_by_folder, r.web_url)
            r.build_ok = record is not None
            r.build_error = build_err
            if not r.build_ok:
                log.warning("  build FAILED: %s", build_err)
                results.append(r)
                continue
            log.info("  build ok")

            # -- Stage 5: validate ---------------------------------------------
            r.validate_errors = _validate(validator, record)
            r.validate_ok = len(r.validate_errors) == 0
            if r.validate_ok:
                log.info("  validate ok")
            else:
                log.warning("  validate INVALID (%d errors)", len(r.validate_errors))
                for e in r.validate_errors[:5]:
                    log.warning("    %s", e)

        results.append(r)

    return results


# ---------------------------------------------------------------------------
# Aggregate analysis and report
# ---------------------------------------------------------------------------

def _aggregate(results: list[ArcResult]) -> dict:
    n_total = len(results)
    n_cloned = sum(1 for r in results if r.clone_ok)
    n_parsed = sum(1 for r in results if r.parse_ok)
    n_built = sum(1 for r in results if r.build_ok)
    n_valid = sum(1 for r in results if r.validate_ok)

    # Parse failures grouped by exception type
    parse_fail_exc: dict[str, list[str]] = defaultdict(list)
    for r in results:
        if r.clone_ok and not r.parse_ok:
            parse_fail_exc[r.parse_exc_type or "Unknown"].append(r.path)

    # Validation error frequency
    val_err_counter: Counter[str] = Counter()
    for r in results:
        for e in r.validate_errors:
            # Normalise to path part only for frequency grouping
            val_err_counter[e] += 1

    # Field richness (over parsed ARCs)
    parsed_results = [r for r in results if r.parse_ok]
    n_p = len(parsed_results)

    def frac(values):
        if n_p == 0:
            return "N/A"
        count = sum(1 for v in values if v)
        return f"{count}/{n_p} ({100*count//n_p}%)"

    richness = {
        "contacts_nonzero": frac([r.n_contacts > 0 for r in parsed_results]),
        "dois_nonzero": frac([r.n_dois > 0 for r in parsed_results]),
        "studies_nonzero": frac([r.n_studies > 0 for r in parsed_results]),
        "assays_nonzero": frac([r.n_assays > 0 for r in parsed_results]),
        "mtype_any_set": frac([r.n_assays_with_mtype > 0 for r in parsed_results]),
    }

    # Omics hit-rate (all assay folders across all parsed ARCs)
    total_omics = sum(r.omics_total for r in parsed_results)
    total_classified = sum(r.omics_classified for r in parsed_results)
    omics_rate = (
        f"{total_classified}/{total_omics} ({100*total_classified//total_omics}%)"
        if total_omics > 0 else "0/0 (N/A)"
    )

    return {
        "n_total": n_total,
        "n_cloned": n_cloned,
        "n_parsed": n_parsed,
        "n_built": n_built,
        "n_valid": n_valid,
        "parse_fail_exc": dict(parse_fail_exc),
        "val_err_counter": val_err_counter.most_common(20),
        "richness": richness,
        "omics_rate": omics_rate,
        "total_omics_folders": total_omics,
    }


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _write_report(results: list[ArcResult], agg: dict) -> Path:
    report_path = REPO_ROOT / "docs" / "progress" / "2026-06-10-plan4-dryrun-postfix.md"

    lines: list[str] = []
    a = lines.append

    a("# Plan 4 Dry-Run Diagnostic Report")
    a("")
    a("**Date:** 2026-06-10  ")
    a(f"**Target:** `{GITLAB_BASE}` (first {SAMPLE_SIZE} public ARCs, max_pages={MAX_PAGES})  ")
    a(
        f"**Headline:** parsed {agg['n_parsed']}/{agg['n_total']}, "
        f"built {agg['n_built']}/{agg['n_total']}, "
        f"validated {agg['n_valid']}/{agg['n_total']}  "
    )
    a("")
    a("---")
    a("")

    # -- Per-ARC table --------------------------------------------------------
    a("## Per-ARC Results")
    a("")
    a(
        "| # | Path | Clone | Parse | Assays | Contacts | DOIs | mtype>0 | Build | Valid |"
        " Val-errors |"
    )
    a("|---|------|-------|-------|--------|----------|------|---------|-------|-------|-----------|")
    for idx, r in enumerate(results, 1):
        clone_s = "ok" if r.clone_ok else "FAIL"
        parse_s = (
            "ok" if r.parse_ok
            else (f"FAIL({r.parse_exc_type})" if r.parse_exc_type else "skip")
        )
        assays_s = str(r.n_assays) if r.parse_ok else "-"
        contacts_s = str(r.n_contacts) if r.parse_ok else "-"
        dois_s = str(r.n_dois) if r.parse_ok else "-"
        mtype_s = str(r.n_assays_with_mtype) if r.parse_ok else "-"
        build_s = "ok" if r.build_ok else ("FAIL" if r.clone_ok and r.parse_ok else "skip")
        valid_s = "ok" if r.validate_ok else ("INVALID" if r.build_ok else "skip")
        n_verr = len(r.validate_errors)
        verr_s = str(n_verr) if n_verr > 0 else "-"
        short_path = r.path.split("/")[-1] if "/" in r.path else r.path
        a(
            f"| {idx} | `{short_path}` | {clone_s} | {parse_s} | {assays_s} | {contacts_s} | "
            f"{dois_s} | {mtype_s} | {build_s} | {valid_s} | {verr_s} |"
        )

    a("")
    a("---")
    a("")

    # -- Aggregate analysis ---------------------------------------------------
    a("## Aggregate Analysis")
    a("")
    a("### Parse success rate")
    a("")
    n_clone_fail = agg["n_total"] - agg["n_cloned"]
    n_parse_fail = agg["n_cloned"] - agg["n_parsed"]
    a(f"- Total ARCs sampled: **{agg['n_total']}**")
    a(f"- Clone failures: **{n_clone_fail}**")
    a(f"- Parse failures (arctrl): **{n_parse_fail}** out of {agg['n_cloned']} successfully cloned")
    a(f"- Parse success rate: **{agg['n_parsed']}/{agg['n_cloned']}** (of cloned ARCs)")
    a("")
    if agg["parse_fail_exc"]:
        a("**Distinct parse-failure exceptions:**")
        a("")
        for exc_type, paths in sorted(agg["parse_fail_exc"].items()):
            a(f"- `{exc_type}` ({len(paths)} ARC(s)): {', '.join(paths)}")
        a("")
    else:
        a("No parse failures observed.")
        a("")

    a("### Build and validate success rate")
    a("")
    a(f"- Build success: **{agg['n_built']}/{agg['n_parsed']}** (of parsed ARCs)")
    a(f"- Validate success: **{agg['n_valid']}/{agg['n_built']}** (of built ARCs)")
    a("")
    if agg["val_err_counter"]:
        a("**Distinct validation failures (field path + message, by frequency):**")
        a("")
        a("| Count | Validation error |")
        a("|-------|-----------------|")
        for msg, cnt in agg["val_err_counter"]:
            safe_msg = msg.replace("|", "\\|")
            a(f"| {cnt} | `{safe_msg}` |")
        a("")
    else:
        a("No validation failures observed.")
        a("")

    a("### Field-richness profile (over parsed ARCs)")
    a("")
    a("Fraction of parsed ARCs that have non-empty values for each field:")
    a("")
    a("| Field | Non-empty fraction |")
    a("|-------|-------------------|")
    rich = agg["richness"]
    a(f"| contacts | {rich['contacts_nonzero']} |")
    a(f"| dois | {rich['dois_nonzero']} |")
    a(f"| studies | {rich['studies_nonzero']} |")
    a(f"| assays (via studies) | {rich['assays_nonzero']} |")
    a(f"| any assay with measurement_type | {rich['mtype_any_set']} |")
    a("")

    a("### Omics classifier hit-rate")
    a("")
    a(
        f"Across all assay folders seen in parsed ARCs: "
        f"**{agg['omics_rate']}** classified to a real domain (not None -> fell back to 'other')."
    )
    a(f"Total assay folders examined: {agg['total_omics_folders']}.")
    a("")

    # -- Implications for Plan 4 ----------------------------------------------
    a("---")
    a("")
    a("## Implications for Plan 4")
    a("")

    n_p = agg["n_parsed"]
    n_t = agg["n_total"]
    n_b = agg["n_built"]
    n_v = agg["n_valid"]

    # Derive bullets from data
    bullets: list[str] = []

    # arctrl robustness
    if n_p == n_t:
        bullets.append(
            f"**arctrl robustness is not the lead problem** - all {n_t} ARCs cloned "
            f"and parsed without exception; parser hardening can be deferred."
        )
    elif n_p >= int(0.8 * n_t):
        bullets.append(
            f"**arctrl is mostly robust** - {n_p}/{n_t} ARCs parsed; "
            f"the {n_t - n_p} failures may warrant defensive wrapping but are not blocking."
        )
    else:
        bullets.append(
            f"**arctrl reliability is a concern** - only {n_p}/{n_t} ARCs parsed; "
            f"exception handling and fallback logic must be the lead Plan 4 task before "
            f"real-scale harvesting."
        )

    # Validation failures
    if agg["val_err_counter"]:
        top_err, top_cnt = agg["val_err_counter"][0]
        bullets.append(
            f"**Schema validation failures are present** - {n_b - n_v}/{n_b} built records "
            f"failed validation; the most common error (x{top_cnt}): `{top_err[:120]}`. "
            f"Plan 4 must fix the corresponding field extraction or schema defaults."
        )
    else:
        bullets.append(
            f"**Skeleton defaults pass validation for all {n_v} built records** - no "
            f"immediate schema-breaking fields; Plan 4 can focus on enriching placeholder "
            f"values without changing the schema contract."
        )

    # contacts richness
    rich = agg["richness"]
    contacts_frac = rich["contacts_nonzero"]
    bullets.append(
        f"**Contact metadata richness:** {contacts_frac} of parsed ARCs have at least "
        f"one contact; Plan 4 contact extraction likely yields real data for most ARCs."
    )

    # DOI richness
    dois_frac = rich["dois_nonzero"]
    bullets.append(
        f"**DOI / publication metadata:** {dois_frac} of parsed ARCs carry DOIs; "
        f"publication extraction is worthwhile but will miss a significant fraction of ARCs."
    )

    # measurement_type / omics classification
    omics_r = agg["omics_rate"]
    mtype_frac = rich["mtype_any_set"]
    bullets.append(
        f"**Omics classification via folder names hits {omics_r}**; "
        f"measurement_type is populated in {mtype_frac} of parsed ARCs - Plan 4 can "
        f"cross-check folder-based classification against the measurement_type field "
        f"to improve accuracy."
    )

    # assay linkage
    assays_frac = rich["assays_nonzero"]
    bullets.append(
        f"**Assay-to-study linkage:** {assays_frac} of parsed ARCs expose at least one "
        f"assay via the studies path; the remaining ARCs will produce placeholder assay "
        f"records - Plan 4 should audit whether these ARCs truly lack assays or if the "
        f"arctrl RegisteredAssayIdentifiers join is incomplete."
    )

    for b in bullets:
        a(f"- {b}")
    a("")

    # -- Full per-ARC details (errors) ----------------------------------------
    a("---")
    a("")
    a("## Detailed Error Listings")
    a("")
    for idx, r in enumerate(results, 1):
        has_detail = (
            r.clone_error or r.parse_error or r.build_error or r.validate_errors
        )
        if not has_detail:
            continue
        a(f"### ARC {idx}: `{r.path}`")
        a("")
        if r.clone_error:
            a(f"**Clone error:** `{r.clone_error}`")
            a("")
        if r.parse_error:
            a(f"**Parse error** (`{r.parse_exc_type}`): `{r.parse_error}`")
            a("")
        if r.build_error:
            a(f"**Build error:** `{r.build_error}`")
            a("")
        if r.validate_errors:
            a(f"**Validation errors ({len(r.validate_errors)}):**")
            a("")
            for e in r.validate_errors:
                a(f"- `{e}`")
            a("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=== Plan 4 dry-run started ===")
    results = run_dryrun()

    if not results:
        log.error("No results - enumeration failed or returned no ARCs. Aborting.")
        sys.exit(1)

    log.info("=== Aggregating results ===")
    agg = _aggregate(results)

    # Print summary to stdout
    print("\n" + "=" * 70)
    print("PLAN 4 DRY-RUN SUMMARY")
    print("=" * 70)
    print(f"ARCs sampled  : {agg['n_total']}")
    print(f"Cloned        : {agg['n_cloned']}/{agg['n_total']}")
    print(f"Parsed (arctrl): {agg['n_parsed']}/{agg['n_total']}")
    print(f"Built          : {agg['n_built']}/{agg['n_total']}")
    print(f"Valid          : {agg['n_valid']}/{agg['n_total']}")
    print(f"Omics hit-rate : {agg['omics_rate']}")
    print("")
    print("Top 5 validation errors:")
    for msg, cnt in agg["val_err_counter"][:5]:
        print(f"  x{cnt}  {msg}")
    print("=" * 70 + "\n")

    log.info("=== Writing report ===")
    report_path = _write_report(results, agg)
    log.info("Report written to: %s", report_path)
    log.info("=== Plan 4 dry-run complete ===")


if __name__ == "__main__":
    main()
