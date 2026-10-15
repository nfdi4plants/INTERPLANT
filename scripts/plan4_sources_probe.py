"""Plan 4 extraction-sources probe: discover arctrl access paths for enrichment fields.

READ-ONLY - does not write to any database or modify any source file.

For each of the first 20 public ARCs at https://git.nfdi4plants.org, this script:
  - clones (shallow, LFS skipped)
  - loads via arctrl.ARC.load
  - probes per-ARC:
      * measurement_type / technology_type  (via arc.Assays)
      * license                             (via arc.License)
      * organism characteristics            (via arc.Studies[*].Tables characteristic columns)
      * experiment_context signal           (arc.Title, arc.Description, study titles,
                                             protocol descriptions)
      * on-disk layout                      (assays/*, dataset/, runs/, workflows/, LICENSE*)

Run with: GIT_LFS_SKIP_SMUDGE=1 uv run python scripts/plan4_sources_probe.py

Author: Mohamed Abouzid m.abouzid@fz-juelich.de
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import traceback
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
log = logging.getLogger("plan4_sources_probe")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
GITLAB_BASE = "https://git.nfdi4plants.org"
MAX_PAGES = 3
SAMPLE_SIZE = 20
CLONE_TIMEOUT_S = 60

# printed once per script run, not per ARC
_STUDY_ATTRS_PRINTED = False
_ARC_INV_ATTRS_PRINTED = False


# ---------------------------------------------------------------------------
# Clone helper (mirrors plan4_dryrun.py)
# ---------------------------------------------------------------------------

def _clone_arc(web_url: str, tmpdir: Path) -> tuple[bool, str]:
    """Shallow-clone an ARC repo; skip LFS blobs. Returns (ok, error_summary)."""
    clone_url = web_url.rstrip("/") + ".git"
    merged_env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}
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


# ---------------------------------------------------------------------------
# Probe helpers
# ---------------------------------------------------------------------------

def _safe_str(val: Any) -> str:
    """Convert a value to a stripped string, returning empty string on None."""
    if val is None:
        return ""
    return str(val).strip()


def _non_dunder_attrs(obj: Any) -> list[str]:
    """Return non-dunder attribute names of an object."""
    return [a for a in dir(obj) if not a.startswith("_")]


def probe_measurement_and_technology(arc: Any, arc_id: str) -> None:
    """Probe assay measurement_type and technology_type."""
    print(f"\n[{arc_id}] === ASSAY TYPES ===")
    assays = arc.Assays or []
    print(f"[{arc_id}] arc.Assays count: {len(assays)}")
    for idx, assay in enumerate(assays):
        try:
            mtype = getattr(assay, "MeasurementType", None)
            ttype = getattr(assay, "TechnologyType", None)
            tplatform = getattr(assay, "TechnologyPlatform", None)
            ident = _safe_str(getattr(assay, "Identifier", f"assay-{idx}"))
            mt_str = _safe_str(mtype)
            tt_str = _safe_str(ttype)
            tp_str = _safe_str(tplatform)
            print(
                f"[{arc_id}]   assay[{idx}] identifier={ident!r}"
                f" MeasurementType={mt_str!r}"
                f" TechnologyType={tt_str!r}"
                f" TechnologyPlatform={tp_str!r}"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[{arc_id}]   assay[{idx}] probe error: {exc}")


def probe_license(arc: Any, arc_id: str) -> None:
    """Probe arc.License and arc.Comments for license entry."""
    print(f"\n[{arc_id}] === LICENSE ===")
    # Direct arc.License attribute (observed in arctrl API)
    try:
        lic = getattr(arc, "License", None)
        print(f"[{arc_id}]   arc.License = {_safe_str(lic)!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{arc_id}]   arc.License error: {exc}")

    # arc.Comments - look for a 'License' comment
    try:
        comments = arc.Comments or []
        print(f"[{arc_id}]   arc.Comments count: {len(comments)}")
        for c in comments:
            name = _safe_str(getattr(c, "Name", ""))
            value = _safe_str(getattr(c, "Value", ""))
            print(f"[{arc_id}]     comment name={name!r} value={value!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{arc_id}]   arc.Comments probe error: {exc}")

    # Investigation-level comments (arc.ISAInvestigation or inner Investigation)
    try:
        inv = getattr(arc, "ISAInvestigation", None)
        if inv is None:
            # Try the registered studies path
            inv = getattr(arc, "ArcInvestigation", None)
        if inv is not None:
            inv_comments = getattr(inv, "Comments", None) or []
            print(f"[{arc_id}]   Investigation.Comments count: {len(inv_comments)}")
            for c in inv_comments:
                name = _safe_str(getattr(c, "Name", ""))
                value = _safe_str(getattr(c, "Value", ""))
                print(f"[{arc_id}]     inv-comment name={name!r} value={value!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{arc_id}]   Investigation.Comments probe error: {exc}")


def probe_organism(arc: Any, arc_id: str) -> None:
    """Probe organism via study characteristics tables."""
    global _STUDY_ATTRS_PRINTED  # noqa: PLW0603
    print(f"\n[{arc_id}] === ORGANISM / CHARACTERISTICS ===")
    studies = arc.Studies or []
    print(f"[{arc_id}]   arc.Studies count: {len(studies)}")
    for sidx, study in enumerate(studies):
        try:
            stitle = _safe_str(getattr(study, "Title", f"study-{sidx}"))
            stitle = stitle or f"study-{sidx}"
            # Print non-dunder attrs once globally for diagnosis
            if not _STUDY_ATTRS_PRINTED:
                attrs = _non_dunder_attrs(study)
                print(f"[GLOBAL]   ArcStudy non-dunder attrs: {attrs}")
                _STUDY_ATTRS_PRINTED = True

            # StudyDesignDescriptors - may encode organism
            try:
                sdd = getattr(study, "StudyDesignDescriptors", None)
                if sdd:
                    for i, d in enumerate(sdd):
                        print(
                            f"[{arc_id}]   study[{sidx}]={stitle!r}"
                            f" StudyDesignDescriptor[{i}]={_safe_str(d)!r}"
                        )
            except Exception as exc:  # noqa: BLE001
                print(f"[{arc_id}]   study[{sidx}] StudyDesignDescriptors error: {exc}")

            # Tables - look for Characteristic[Organism] or similar columns
            try:
                tables = getattr(study, "Tables", None) or []
                print(
                    f"[{arc_id}]   study[{sidx}]={stitle!r} Tables count: {len(tables)}"
                )
                for tidx, table in enumerate(tables):
                    _probe_table_for_organism(arc_id, sidx, stitle, tidx, table)
            except Exception as exc:  # noqa: BLE001
                print(f"[{arc_id}]   study[{sidx}] Tables probe error: {exc}")

            # Fallback: check for any attr containing Table/Sample/Material/Characteristic
            for attr in dir(study):
                if attr.startswith("_"):
                    continue
                if any(k in attr for k in ("Table", "Sample", "Material", "Characteristic")):
                    try:
                        val = getattr(study, attr)
                        if callable(val):
                            continue
                        print(
                            f"[{arc_id}]   study[{sidx}] attr={attr!r} value={repr(val)[:120]}"
                        )
                    except Exception:  # noqa: BLE001
                        pass

        except Exception as exc:  # noqa: BLE001
            print(f"[{arc_id}]   study[{sidx}] outer probe error: {exc}")


def _probe_table_for_organism(
    arc_id: str, sidx: int, stitle: str, tidx: int, table: Any
) -> None:
    """Check an ArcTable for Characteristic[Organism] columns and print sample values."""
    try:
        headers = getattr(table, "Headers", None) or []
        tname = _safe_str(getattr(table, "Name", f"table-{tidx}")) or f"table-{tidx}"
        char_organism_cols: list[int] = []
        for colidx, header in enumerate(headers):
            try:
                is_char = getattr(header, "is_characteristic", False)
                if callable(is_char):
                    is_char = is_char()
                header_str = _safe_str(header).lower()
                if is_char and ("organism" in header_str or "species" in header_str):
                    char_organism_cols.append(colidx)
                    print(
                        f"[{arc_id}]     study[{sidx}]={stitle!r}"
                        f" table={tname!r}"
                        f" col[{colidx}] ORGANISM header={_safe_str(header)!r}"
                    )
                elif "organism" in header_str or "species" in header_str:
                    char_organism_cols.append(colidx)
                    print(
                        f"[{arc_id}]     study[{sidx}]={stitle!r}"
                        f" table={tname!r}"
                        f" col[{colidx}] species-like header={_safe_str(header)!r}"
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"[{arc_id}]     header[{colidx}] probe error: {exc}")

        # For each matched column, dump first few cell values
        if char_organism_cols:
            try:
                columns = getattr(table, "Columns", None) or []
                for colidx in char_organism_cols:
                    if colidx < len(columns):
                        col = columns[colidx]
                        cells = getattr(col, "Cells", None) or []
                        sample_vals = [_safe_str(c) for c in cells[:5]]
                        print(
                            f"[{arc_id}]     col[{colidx}] sample cell values: {sample_vals}"
                        )
            except Exception as exc:  # noqa: BLE001
                print(f"[{arc_id}]     column cell probe error: {exc}")

        # Even if no organism col found, print all characteristic-like columns
        if not char_organism_cols:
            for colidx, header in enumerate(headers):
                try:
                    is_char = getattr(header, "is_characteristic", False)
                    if callable(is_char):
                        is_char = is_char()
                    if is_char:
                        print(
                            f"[{arc_id}]     study[{sidx}]={stitle!r}"
                            f" table={tname!r}"
                            f" col[{colidx}] characteristic header={_safe_str(header)!r}"
                        )
                except Exception:  # noqa: BLE001
                    pass
    except Exception as exc:  # noqa: BLE001
        print(f"[{arc_id}]   table[{tidx}] probe error: {exc}")


def probe_context_signal(arc: Any, arc_id: str) -> None:
    """Probe experiment context: title, description, study titles, protocol descriptions."""
    print(f"\n[{arc_id}] === CONTEXT SIGNAL ===")
    try:
        title = _safe_str(getattr(arc, "Title", None))
        description = _safe_str(getattr(arc, "Description", None))
        print(f"[{arc_id}]   arc.Title={title!r}")
        print(f"[{arc_id}]   arc.Description={description[:200]!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{arc_id}]   Title/Description probe error: {exc}")

    studies = arc.Studies or []
    for sidx, study in enumerate(studies):
        try:
            stitle = _safe_str(getattr(study, "Title", None))
            sdesc = _safe_str(getattr(study, "Description", None))
            print(f"[{arc_id}]   study[{sidx}].Title={stitle!r}")
            if sdesc:
                print(f"[{arc_id}]   study[{sidx}].Description={sdesc[:200]!r}")
            # Look for protocol descriptions in study tables
            tables = getattr(study, "Tables", None) or []
            for tidx, table in enumerate(tables):
                try:
                    # GetProtocolDescriptionColumn
                    pdesc_col = None
                    try:
                        pdesc_col = table.GetProtocolDescriptionColumn()
                    except Exception:  # noqa: BLE001
                        pass
                    if pdesc_col is not None:
                        cells = getattr(pdesc_col, "Cells", None) or []
                        for c in cells[:3]:
                            val = _safe_str(c)
                            if val:
                                print(
                                    f"[{arc_id}]   study[{sidx}] table[{tidx}]"
                                    f" protocol_desc={val[:150]!r}"
                                )
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            print(f"[{arc_id}]   study[{sidx}] context probe error: {exc}")


def probe_disk_layout(arc_root: Path, arc_id: str) -> None:
    """List assays/* subfolders and presence of dataset/, runs/, workflows/, LICENSE*."""
    print(f"\n[{arc_id}] === DISK LAYOUT ===")
    try:
        assays_dir = arc_root / "assays"
        if assays_dir.is_dir():
            subfolders = sorted(p.name for p in assays_dir.iterdir() if p.is_dir())
            print(f"[{arc_id}]   assays/ subfolders: {subfolders}")
        else:
            print(f"[{arc_id}]   assays/ not present")

        for subdir in ("dataset", "runs", "workflows"):
            present = (arc_root / subdir).is_dir()
            print(f"[{arc_id}]   {subdir}/ present: {present}")

        license_files = sorted(p.name for p in arc_root.glob("LICENSE*"))
        print(f"[{arc_id}]   LICENSE* files: {license_files}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{arc_id}]   disk layout probe error: {exc}")


# ---------------------------------------------------------------------------
# Main probe loop
# ---------------------------------------------------------------------------

def run_probe() -> None:
    sys.path.insert(0, str(REPO_ROOT))
    import arctrl  # noqa: F401 - verify import once

    from harvester.enumerate import iter_public_arcs

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
        return

    log.info("Enumerated %d ARCs; processing up to %d ...", len(arcs_meta), SAMPLE_SIZE)

    n_cloned = 0
    n_loaded = 0
    arc_results: list[dict] = []

    for idx, meta in enumerate(arcs_meta, 1):
        path = meta["path_with_namespace"]
        web_url = meta["web_url"]
        arc_id = path.split("/")[-1] if "/" in path else path
        log.info("[%d/%d] %s", idx, len(arcs_meta), path)

        result: dict = {
            "idx": idx, "path": path, "arc_id": arc_id, "cloned": False, "loaded": False
        }
        arc_results.append(result)

        with tempfile.TemporaryDirectory(prefix="plan4_probe_") as tmpdir:
            arc_root = Path(tmpdir)

            # -- Clone ---------------------------------------------------------
            clone_ok, clone_err = _clone_arc(web_url, arc_root)
            if not clone_ok:
                log.warning("  clone FAILED: %s", clone_err)
                print(f"\n[{arc_id}] CLONE FAILED: {clone_err}")
                continue
            n_cloned += 1
            result["cloned"] = True
            log.info("  clone ok")

            # -- Load via arctrl -----------------------------------------------
            try:
                arc = arctrl.ARC.load(str(arc_root))
                n_loaded += 1
                result["loaded"] = True
                log.info("  arctrl.ARC.load ok")
            except Exception as exc:  # noqa: BLE001
                log.warning("  arctrl.ARC.load FAILED: %s", exc)
                print(f"\n[{arc_id}] ARC.load FAILED: {type(exc).__name__}: {exc}")
                continue

            print(f"\n{'='*60}")
            print(f"[{arc_id}] ARC #{idx}: {path}")
            print(f"{'='*60}")

            # -- 1: measurement_type / technology_type -------------------------
            try:
                probe_measurement_and_technology(arc, arc_id)
            except Exception as exc:  # noqa: BLE001
                print(f"[{arc_id}] measurement/technology probe EXCEPTION: {exc}")

            # -- 2: license ----------------------------------------------------
            try:
                probe_license(arc, arc_id)
            except Exception as exc:  # noqa: BLE001
                print(f"[{arc_id}] license probe EXCEPTION: {exc}")

            # -- 3: organism characteristics -----------------------------------
            try:
                probe_organism(arc, arc_id)
            except Exception as exc:  # noqa: BLE001
                print(f"[{arc_id}] organism probe EXCEPTION: {exc}")

            # -- 4: experiment context signal ----------------------------------
            try:
                probe_context_signal(arc, arc_id)
            except Exception as exc:  # noqa: BLE001
                print(f"[{arc_id}] context signal probe EXCEPTION: {exc}")

            # -- 5: on-disk layout ---------------------------------------------
            try:
                probe_disk_layout(arc_root, arc_id)
            except Exception as exc:  # noqa: BLE001
                print(f"[{arc_id}] disk layout probe EXCEPTION: {exc}")

    print("\n" + "=" * 60)
    print("PROBE SUMMARY")
    print("=" * 60)
    print(f"ARCs enumerated : {len(arcs_meta)}")
    print(f"ARCs cloned     : {n_cloned}/{len(arcs_meta)}")
    print(f"ARCs loaded     : {n_loaded}/{len(arcs_meta)}")
    print("=" * 60)
    log.info("Probe complete: cloned=%d loaded=%d total=%d", n_cloned, n_loaded, len(arcs_meta))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_probe()
