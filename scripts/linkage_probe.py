"""Linkage investigation probe - READ-ONLY diagnostic script.

For each of the first 5 zero-assay ARCs (those that IsaReader returns 0 assays for),
inspect the raw arctrl ARC object directly to determine whether:
  (A) the ARC has assays but they are being dropped by the join in IsaReader
  (B) the ARC genuinely has no registered assays

Evidence collected per ARC:
  - arc.Assays count and Identifier values
  - arc.Studies with each study's Identifier and RegisteredAssayIdentifiers
  - Whether assay identifiers match registered strings (exact, case, path prefix)
  - Whether an assays/ directory with isa.assay.xlsx files physically exists on disk

Run with:  uv run python scripts/linkage_probe.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

GITLAB_BASE = "https://git.nfdi4plants.org"
MAX_PAGES = 3
CLONE_TIMEOUT_S = 90
TARGET_ZERO_ASSAY_COUNT = 5


def clone_arc(web_url: str, dest: Path) -> tuple[bool, str]:
    clone_url = web_url.rstrip("/") + ".git"
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(dest)],
            capture_output=True,
            text=True,
            timeout=CLONE_TIMEOUT_S,
            env=env,
        )
        if result.returncode != 0:
            summary = (result.stderr or result.stdout or "").strip()
            return False, summary[:300]
        return True, ""
    except subprocess.TimeoutExpired:
        return False, f"clone timed out after {CLONE_TIMEOUT_S}s"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def count_isa_assay_files_on_disk(arc_root: Path) -> list[str]:
    """Return list of paths to isa.assay.xlsx files found under arc_root/assays/."""
    assays_dir = arc_root / "assays"
    if not assays_dir.is_dir():
        return []
    found = []
    for xlsx in assays_dir.rglob("isa.assay.xlsx"):
        found.append(str(xlsx.relative_to(arc_root)))
    return found


def list_assay_subdirs(arc_root: Path) -> list[str]:
    """Return names of immediate subdirs under arc_root/assays/ (the assay folders)."""
    assays_dir = arc_root / "assays"
    if not assays_dir.is_dir():
        return []
    return [d.name for d in sorted(assays_dir.iterdir()) if d.is_dir()]


def probe_arc_raw(arc_root: Path) -> dict:
    """Directly inspect the arctrl ARC object - does NOT go through IsaReader."""
    import arctrl

    arc = arctrl.ARC.load(str(arc_root))

    # Flat assay list
    raw_assays = list(arc.Assays or [])
    assay_identifiers = []
    for a in raw_assays:
        ident = getattr(a, "Identifier", None)
        assay_identifiers.append(str(ident) if ident is not None else None)

    # Studies
    raw_studies = list(arc.Studies or [])
    studies_info = []
    for s in raw_studies:
        sid = str(s.Identifier) if s.Identifier is not None else None
        reg_ids = list(getattr(s, "RegisteredAssayIdentifiers", []) or [])
        reg_ids_str = [str(r) for r in reg_ids]
        studies_info.append({
            "identifier": sid,
            "registered_assay_identifiers": reg_ids_str,
        })

    # Cross-check: for each assay, does it appear in any study's registered list?
    match_analysis = []
    for a_ident in assay_identifiers:
        if a_ident is None:
            match_analysis.append({"assay_identifier": None, "status": "assay-has-no-identifier"})
            continue
        found_exact = False
        found_case_insensitive = False
        found_basename = False
        found_strip = False
        for s in studies_info:
            reg = s["registered_assay_identifiers"]
            if a_ident in reg:
                found_exact = True
                break
            # case-insensitive
            if any(r.lower() == a_ident.lower() for r in reg):
                found_case_insensitive = True
            # basename matching (e.g. "assays/foo" vs "foo")
            a_base = a_ident.split("/")[-1].strip()
            if any(r.split("/")[-1].strip() == a_base for r in reg):
                found_basename = True
            # strip whitespace
            if any(r.strip() == a_ident.strip() for r in reg):
                found_strip = True

        if found_exact:
            status = "MATCHED-exact"
        elif found_strip:
            status = "MATCHED-after-strip-whitespace"
        elif found_case_insensitive:
            status = "MISMATCH-case-only"
        elif found_basename:
            status = "MISMATCH-path-prefix"
        elif not any(s["registered_assay_identifiers"] for s in studies_info):
            status = "NO-REGISTERED-IDS-IN-ANY-STUDY"
        else:
            status = "UNREGISTERED-no-study-links-this-assay"

        match_analysis.append({"assay_identifier": a_ident, "status": status})

    # Also check: does IsaReader join produce zero assays?
    from harvester.isa_reader import IsaReader
    try:
        investigation = IsaReader().read(arc_root)
        isareader_assay_count = sum(len(s.assays) for s in investigation.studies)
        isareader_n_studies = len(investigation.studies)
    except Exception as exc:  # noqa: BLE001
        isareader_assay_count = -1
        isareader_n_studies = -1

    return {
        "arc_assays_count": len(raw_assays),
        "assay_identifiers": assay_identifiers,
        "studies": studies_info,
        "match_analysis": match_analysis,
        "isareader_assay_count": isareader_assay_count,
        "isareader_n_studies": isareader_n_studies,
    }


def main():
    from harvester.enumerate import iter_public_arcs

    print("Enumerating public ARCs ...")
    arcs_meta = []
    for meta in iter_public_arcs(GITLAB_BASE, max_pages=MAX_PAGES):
        arcs_meta.append(meta)
        if len(arcs_meta) >= 50:  # collect more to find 5 zero-assay cases
            break

    print(f"  -> found {len(arcs_meta)} public ARCs")

    results = []
    zero_assay_found = 0

    for idx, meta in enumerate(arcs_meta, 1):
        if zero_assay_found >= TARGET_ZERO_ASSAY_COUNT:
            break

        path = meta["path_with_namespace"]
        web_url = meta["web_url"]
        print(f"\n[{idx}] {path}")

        with tempfile.TemporaryDirectory(prefix="linkage_probe_") as tmpdir:
            arc_root = Path(tmpdir)
            ok, err = clone_arc(web_url, arc_root)
            if not ok:
                print(f"  CLONE FAILED: {err}")
                continue

            # Quick IsaReader check to see if this is a zero-assay ARC
            try:
                from harvester.isa_reader import IsaReader
                inv = IsaReader().read(arc_root)
                assay_count_via_reader = sum(len(s.assays) for s in inv.studies)
            except Exception as exc:  # noqa: BLE001
                print(f"  IsaReader failed: {exc}")
                continue

            if assay_count_via_reader > 0:
                print(f"  -> IsaReader found {assay_count_via_reader} assay(s) - SKIP (not zero-assay)")
                continue

            # This is a zero-assay ARC - do the full probe
            zero_assay_found += 1
            print(f"  -> IsaReader: 0 assays. Starting deep probe ...")

            # Disk inspection
            assay_subdirs = list_assay_subdirs(arc_root)
            isa_assay_files = count_isa_assay_files_on_disk(arc_root)

            # Raw arctrl probe
            try:
                probe = probe_arc_raw(arc_root)
            except Exception as exc:  # noqa: BLE001
                print(f"  probe_arc_raw failed: {exc}")
                continue

            result = {
                "path": path,
                "web_url": web_url,
                "assay_subdirs_on_disk": assay_subdirs,
                "isa_assay_files_on_disk": isa_assay_files,
                **probe,
            }
            results.append(result)

            # Print findings immediately
            print(f"  arc.Assays count: {probe['arc_assays_count']}")
            print(f"  arc.Assays identifiers: {probe['assay_identifiers']}")
            print(f"  arc.Studies count: {len(probe['studies'])}")
            for s in probe["studies"]:
                print(f"    Study '{s['identifier']}' RegisteredAssayIdentifiers: {s['registered_assay_identifiers']}")
            print(f"  Match analysis: {probe['match_analysis']}")
            print(f"  assays/ subdirs on disk: {assay_subdirs}")
            print(f"  isa.assay.xlsx files on disk: {isa_assay_files}")

    print(f"\n\n{'='*70}")
    print(f"LINKAGE INVESTIGATION SUMMARY  ({len(results)} zero-assay ARCs probed)")
    print(f"{'='*70}")

    verdict_counts = {
        "A-bug-dropped": 0,
        "B-genuinely-no-assays": 0,
        "A-bug-no-registered": 0,
    }

    for r in results:
        path = r["path"]
        arc_assay_count = r["arc_assays_count"]
        has_disk_assays = bool(r["assay_subdirs_on_disk"]) or bool(r["isa_assay_files_on_disk"])
        match_statuses = [m["status"] for m in r["match_analysis"]]

        print(f"\n--- {path} ---")
        print(f"  arc.Assays: {arc_assay_count}")
        print(f"  assays/ subdirs on disk: {r['assay_subdirs_on_disk']}")
        print(f"  isa.assay.xlsx on disk: {r['isa_assay_files_on_disk']}")
        print(f"  match statuses: {match_statuses}")

        if arc_assay_count == 0 and not has_disk_assays:
            verdict = "B - genuinely no assays (no arc.Assays, no disk assays)"
            verdict_counts["B-genuinely-no-assays"] += 1
        elif arc_assay_count > 0 and "MATCHED-exact" not in match_statuses and all(
            s == "NO-REGISTERED-IDS-IN-ANY-STUDY" for s in match_statuses
        ):
            verdict = "A - BUG: arc has assays but no study registers them (RegisteredAssayIdentifiers is empty)"
            verdict_counts["A-bug-no-registered"] += 1
        elif arc_assay_count > 0 and any(
            s in ("MISMATCH-case-only", "MISMATCH-path-prefix", "UNREGISTERED-no-study-links-this-assay")
            for s in match_statuses
        ):
            verdict = "A - BUG: arc has assays but identifiers do not match registered strings"
            verdict_counts["A-bug-dropped"] += 1
        elif arc_assay_count == 0 and has_disk_assays:
            verdict = "A? - arc.Assays empty but disk has assay folders (arctrl not loading assays)"
            verdict_counts["A-bug-dropped"] += 1
        else:
            verdict = "B - genuinely no assays"
            verdict_counts["B-genuinely-no-assays"] += 1

        print(f"  VERDICT: {verdict}")

    print(f"\n\nVERDICT COUNTS: {verdict_counts}")
    print(f"Total zero-assay ARCs probed: {len(results)}")

    return results


if __name__ == "__main__":
    main()
