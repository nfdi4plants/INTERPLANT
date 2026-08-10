"""Write the per-run audit artifact: machine-readable JSON + human Markdown.

Takes a BatchReport (duck-typed) and an output directory. The run_timestamp on the
report drives the filenames, so this module performs no clock access.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path


def aggregate(report) -> dict:
    o = report.outcomes
    return {
        "n_total": len(o),
        "n_cloned": sum(1 for r in o if r.clone_ok),
        "n_parsed": sum(1 for r in o if r.parse_ok),
        "n_built": sum(1 for r in o if r.build_ok),
        "n_valid": sum(1 for r in o if r.validate_ok),
        "n_filtered": sum(1 for r in o if r.filtered),
        "n_suppressed": sum(1 for r in o if r.suppressed_by),
        "n_upserted": sum(1 for r in o if r.upsert_ok),
        "omics_classified": sum(r.omics_classified for r in o),
        "omics_total": sum(r.omics_total for r in o),
    }


def write_run_report(report, out_dir) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = report.run_timestamp
    json_path = out_dir / f"harvest-{stamp}.json"
    md_path = out_dir / f"harvest-{stamp}.md"

    agg = aggregate(report)
    json_path.write_text(
        json.dumps(
            {
                "source": report.source,
                "run_timestamp": stamp,
                "gitlab_base": report.gitlab_base,
                "verdict": report.verdict,
                "verdict_reason": report.verdict_reason,
                "totals": agg,
                "outcomes": [asdict(r) for r in report.outcomes],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    lines: list[str] = []
    a = lines.append
    a("# Batch Harvest Report")
    a("")
    a(f"- Run: `{stamp}`  Source: `{report.source}`  Verdict: **{report.verdict}**")
    a(
        f"- Totals: enumerated {agg['n_total']}, cloned {agg['n_cloned']}, "
        f"parsed {agg['n_parsed']}, filtered {agg['n_filtered']}, "
        f"built {agg['n_built']}, validated {agg['n_valid']}, "
        f"suppressed {agg['n_suppressed']}, upserted {agg['n_upserted']}"
    )
    omics = (
        f"{agg['omics_classified']}/{agg['omics_total']}"
        if agg["omics_total"] else "0/0"
    )
    a(f"- Omics classified: {omics}")
    a("")
    a("## Per-ARC outcomes")
    a("")
    a("| ARC | Clone | Parse | Build | Valid | Upsert | Title | Record id | Errors |")
    a("|-----|-------|-------|-------|-------|--------|-------|-----------|--------|")
    for r in report.outcomes:
        err = r.clone_error or r.parse_error or r.build_error or (
            "; ".join(r.validate_errors[:2]) if r.validate_errors else r.upsert_error
        )
        err_cell = (err or "-").replace("|", "\\|")[:120]
        title_cell = (r.title or "-").replace("|", "\\|")[:60]
        a(
            f"| {r.path} | {_b(r.clone_ok)} | {_b(r.parse_ok)} | {_b(r.build_ok)} | "
            f"{_b(r.validate_ok)} | {_b(r.upsert_ok)} | {title_cell} | "
            f"{r.record_id or '-'} | {err_cell} |"
        )
    a("")

    # Failure breakdown by parse-exception type.
    parse_fails: Counter[str] = Counter(
        r.parse_exc_type
        for r in report.outcomes
        if r.clone_ok and not r.parse_ok and r.parse_exc_type
    )
    if parse_fails:
        a("## Parse failures by exception")
        a("")
        for exc_type, cnt in parse_fails.most_common():
            a(f"- `{exc_type}`: {cnt}")
        a("")

    excluded = [r for r in report.outcomes if r.filtered]
    if excluded:
        a("## Excluded by policy")
        a("")
        a("| ARC | Rule |")
        a("|-----|------|")
        for r in excluded:
            a(f"| {r.path} | {r.filter_rule} |")
        a("")

    suppressed = [r for r in report.outcomes if r.suppressed_by]
    if suppressed:
        a("## Deduped mirrors")
        a("")
        a("| Suppressed ARC | Record id | Kept namespace |")
        a("|----------------|-----------|----------------|")
        for r in suppressed:
            a(f"| {r.path} | {r.record_id} | {r.suppressed_by} |")
        a("")

    registry = getattr(report, "registry", None)
    if registry is not None and registry.reviews:
        a("## Collisions needing review")
        a("")
        a("| Kept ARC | Title | Colliding ARC | Title | New id |")
        a("|----------|-------|---------------|-------|--------|")
        for held, incoming, new_id in registry.reviews:
            held_title_cell = held.title.replace("|", "\\|")[:40]
            incoming_title_cell = incoming.title.replace("|", "\\|")[:40]
            a(
                f"| {held.namespace} | {held_title_cell} | {incoming.namespace} | "
                f"{incoming_title_cell} | {new_id} |"
            )
        a("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def _b(ok: bool) -> str:
    return "ok" if ok else "-"
