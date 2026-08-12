#!/usr/bin/env python3
"""Reconcile a harvest run report against the record-id collision policy.

Reads a `harvest-<stamp>.json` audit artifact and answers the questions the
audit Markdown leaves to the reader:

1. Does the funnel add up? Every enumerated ARC must land in exactly one
   terminal state, and the states must sum to `n_total`.
2. What did the policy filters exclude? Listed in full, because over-filtering
   is the one failure mode that loses data instead of merely duplicating it.
3. Which mirrors collapsed, and onto whom?
4. Which collisions were held apart by the title guard?
5. Does any collision group contain a same-namespace pair? That is the only
   group shape whose winner depends on the `uniqueId` tiebreak.

Exit code is 1 if the funnel does not reconcile, else 0. Everything else is
reported for a human to judge - this script deliberately does not decide
whether an exclusion was *correct*.

Usage:
    python scripts/verify_collision_run.py harvest-runs/harvest-<stamp>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit


def namespace_of(web_url: str) -> str:
    """Everything in the GitLab path except the repository segment.

    Mirrors harvester.dedup.namespace_of but takes the ARC web url straight
    from the report, so this script stays runnable against an old artifact
    whose code no longer matches HEAD.
    """
    parts = [p for p in urlsplit(web_url).path.strip("/").split("/") if p]
    return "/".join(parts[:-1]) if len(parts) > 1 else ""


def terminal_state(rec: dict) -> str:
    """The single bucket an ARC ended in. Order matches the pipeline's."""
    if not rec.get("clone_ok"):
        return "clone_failed"
    if rec.get("filtered"):
        return "filtered"
    if not rec.get("parse_ok"):
        return "parse_failed"
    if not rec.get("build_ok"):
        return "build_failed"
    if not rec.get("validate_ok"):
        return "validation_failed"
    if rec.get("suppressed_by"):
        return "suppressed"
    return "would_write"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def report(data: dict) -> int:
    outcomes = data["outcomes"]
    totals = data["totals"]
    out: list[str] = []
    a = out.append
    problems: list[str] = []

    buckets: dict[str, list[dict]] = defaultdict(list)
    for rec in outcomes:
        buckets[terminal_state(rec)].append(rec)

    a(f"# Collision verification - run {data['run_timestamp']} ({data['source']})")
    a("")

    # --- Q1: funnel reconciliation -------------------------------------
    a("## Q1 Funnel")
    a("")
    n_total = totals["n_total"]
    if len(outcomes) != n_total:
        problems.append(f"n_total={n_total} but {len(outcomes)} outcome rows")
    order = [
        "clone_failed", "parse_failed", "build_failed", "validation_failed",
        "filtered", "suppressed", "would_write",
    ]
    a("| Terminal state | ARCs |")
    a("|---|---|")
    for state in order:
        a(f"| {state} | {len(buckets[state])} |")
    summed = sum(len(buckets[s]) for s in order)
    a(f"| **sum** | **{summed}** |")
    a(f"| enumerated | {n_total} |")
    a("")
    if summed != n_total:
        problems.append(
            f"terminal states sum to {summed}, enumerated {n_total} - "
            f"{n_total - summed} ARC(s) unaccounted for"
        )

    # A dry run cannot upsert: conn is None, so n_upserted is always 0 and the
    # would-write count is n_valid - n_suppressed rather than n_upserted.
    would_write = len(buckets["would_write"])
    a(f"- would-write records: **{would_write}**")
    a(f"- `n_upserted` in report: {totals['n_upserted']}"
      f"{' (expected 0 for a dry run)' if data['source'] else ''}")
    a(f"- omics classified: {totals['omics_classified']}/{totals['omics_total']}")
    a("")

    # Distinct-id sanity: no two ARCs may reach would_write under one id.
    written_ids: dict[str, list[str]] = defaultdict(list)
    for rec in buckets["would_write"]:
        written_ids[rec["record_id"]].append(rec["path"])
    clashes = {rid: paths for rid, paths in written_ids.items() if len(paths) > 1}
    if clashes:
        problems.append(f"{len(clashes)} record id(s) still claimed by >1 ARC")
        a("### Unresolved id clashes (POLICY FAILURE)")
        a("")
        for rid, paths in sorted(clashes.items()):
            a(f"- `{rid}`: {', '.join(paths)}")
        a("")
    else:
        a(f"- distinct would-write ids: {len(written_ids)} (no clashes)")
        a("")

    # --- Q2: exclusions -------------------------------------------------
    a("## Q2 Excluded by policy - judge each one")
    a("")
    excluded = buckets["filtered"]
    if not excluded:
        a("None.")
    else:
        colliding = _collision_groups(outcomes)
        a("| ARC | Rule | Record id | In a collision group? |")
        a("|---|---|---|---|")
        for rec in sorted(excluded, key=lambda r: r["path"]):
            rid = rec.get("record_id") or "-"
            shared = "yes" if rid in colliding else "**no - unique record**"
            a(f"| {rec['path']} | {rec.get('filter_rule', '-')} | {rid} | {shared} |")
        a("")
        a("An excluded ARC that is **not** in a collision group is data the run "
          "drops outright rather than deduplicates. Those rows need a human to "
          "confirm the ARC really is an unedited template.")
    a("")

    # --- Q3: mirror collapses -------------------------------------------
    a("## Q3 Deduped mirrors")
    a("")
    suppressed = buckets["suppressed"]
    if not suppressed:
        a("None.")
    else:
        a("| Suppressed ARC | Record id | Kept namespace | Suppressed last_activity_at |")
        a("|---|---|---|---|")
        for rec in sorted(suppressed, key=lambda r: r["record_id"]):
            a(f"| {rec['path']} | {rec['record_id']} | {rec['suppressed_by']} | "
              f"{rec.get('last_activity_at') or '-'} |")
        a("")
        a(f"{len(suppressed)} ARC(s) collapsed into a mirror.")
    a("")

    # --- Q4: title guard ------------------------------------------------
    a("## Q4 Held apart by the title guard")
    a("")
    disambiguated = [r for r in outcomes if r.get("disambiguated_to")]
    if not disambiguated:
        a("None. Every collision this run saw was judged a mirror.")
    else:
        a("| ARC | Original id | Disambiguated to | Title |")
        a("|---|---|---|---|")
        for rec in sorted(disambiguated, key=lambda r: r["path"]):
            base = rec["disambiguated_to"].rsplit("-", 1)[0]
            title = (rec.get("title") or "-").replace("|", r"\|")[:50]
            a(f"| {rec['path']} | {base} | {rec['disambiguated_to']} | {title} |")
        a("")
    a("")

    # --- Q5: same-namespace ties ----------------------------------------
    a("## Q5 Groups needing the uniqueId tiebreak")
    a("")
    groups = _collision_groups(outcomes)
    tied = []
    for rid, recs in sorted(groups.items()):
        spaces = [namespace_of(r.get("web_url") or "") for r in recs]
        if len(set(spaces)) < len(spaces):
            tied.append((rid, recs))
    a(f"Collision groups observed (pre-resolution): **{len(groups)}** covering "
      f"{sum(len(v) for v in groups.values())} ARCs.")
    a("")
    if not tied:
        a("No group contains a same-namespace pair, so no winner in this run "
          "was decided by the `uniqueId` tiebreak. That path stays unit-proven "
          "and corpus-unexercised.")
    else:
        a("| Record id | ARCs sharing a namespace |")
        a("|---|---|")
        for rid, recs in tied:
            a(f"| `{rid}` | {', '.join(r['path'] for r in recs)} |")
        a("")
        a("These winners depend on the `uniqueId` tiebreak. Confirm the kept ARC "
          "is the intended one - lexicographic uuid order is stable but arbitrary.")
    a("")

    a("## Verdict")
    a("")
    if problems:
        a("**FAILED** - the funnel does not reconcile:")
        a("")
        for p in problems:
            a(f"- {p}")
    else:
        a("**Funnel reconciles.** Every enumerated ARC lands in exactly one "
          "terminal state and no id is claimed twice. Q2-Q5 above still need "
          "human judgement.")

    print("\n".join(out))
    return 1 if problems else 0


def _collision_groups(outcomes: list[dict]) -> dict[str, list[dict]]:
    """ARCs grouped by the id they *minted*, keeping only contested ids.

    Keyed on the pre-disambiguation id so a group stays visible after the
    registry has split it: a disambiguated ARC reports the suffixed id in
    `record_id`, and grouping on that would hide the collision it came from.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for rec in outcomes:
        rid = rec.get("record_id")
        if not rid:
            continue
        if rec.get("disambiguated_to") == rid:
            rid = rid.rsplit("-", 1)[0]
        groups[rid].append(rec)
    return {rid: recs for rid, recs in groups.items() if len(recs) > 1}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Path to harvest-<stamp>.json")
    args = parser.parse_args(argv)
    if not args.report.exists():
        print(f"No such report: {args.report}", file=sys.stderr)
        return 2
    return report(load(args.report))


if __name__ == "__main__":
    raise SystemExit(main())
