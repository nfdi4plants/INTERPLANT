"""Offline accuracy gate for the omics classifier against the gold set.

Feeds each gold row's stored signals through classify_omics and compares the
result to the human-reviewed gold_domain. No network, no cloning.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

from harvester.classifiers.omics import classify_omics

_GOLD = Path(__file__).parents[2] / "harvester" / "classifiers" / "testdata" / "omics_gold.yaml"

# Regression gate. Achieved accuracy against the human-reviewed gold set is
# 39/97 = 40.2% (up from a 26.8% baseline). Locked 5 points below that so the
# gate catches a real regression without flapping on minor vocab tweaks.
# Context: on the 41 gold rows that carry any measurement/technology signal,
# accuracy is 65.9%; the remainder are folder-name-only rows the per-folder
# classifier cannot resolve without ARC-level context (out of scope here).
MIN_ACCURACY = 0.35


def _load_rows() -> list[dict]:
    data = yaml.safe_load(_GOLD.read_text(encoding="utf-8"))
    return data["rows"]


def _predict(row: dict) -> str:
    domain = classify_omics(
        row.get("folder", "") or "",
        row.get("measurement_type") or None,
        technology_type=row.get("technology_type") or None,
        technology_platform=row.get("technology_platform") or None,
    )
    return domain or "other"


def test_accuracy_against_gold() -> None:
    rows = _load_rows()
    assert rows, "gold set is empty"
    correct = sum(1 for r in rows if _predict(r) == r["gold_domain"])
    accuracy = correct / len(rows)
    # Confusion: (gold -> predicted) counts for mismatches, printed for tuning.
    confusion: Counter[tuple[str, str]] = Counter()
    for r in rows:
        pred = _predict(r)
        if pred != r["gold_domain"]:
            confusion[(r["gold_domain"], pred)] += 1
    print(f"\nomics accuracy: {correct}/{len(rows)} = {accuracy:.1%}")
    if confusion:
        print("mismatches (gold -> predicted): count")
        for (gold, pred), n in confusion.most_common():
            print(f"  {gold} -> {pred}: {n}")
    assert accuracy >= MIN_ACCURACY
