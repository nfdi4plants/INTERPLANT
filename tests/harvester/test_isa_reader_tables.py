"""Tests for the Table dataclass and Investigation.tables."""
from __future__ import annotations

from harvester.isa_reader import Investigation, Table


def test_table_is_constructible_with_parallel_headers_and_columns() -> None:
    table = Table(
        name="3604_indviduals_metadata",
        source="studies/initial_data/isa.study.xlsx#3604_indviduals_metadata",
        headers=["Parameter [latitude]", "Parameter [longitude]"],
        columns=[["18.48583333"], ["-99.79166667"]],
    )
    assert table.headers[0] == "Parameter [latitude]"
    assert table.columns[0] == ["18.48583333"]
    assert table.source.endswith("#3604_indviduals_metadata")


def test_investigation_tables_defaults_to_empty() -> None:
    # Every existing Investigation(...) call site omits `tables`; adding the
    # field must not break them.
    inv = Investigation(identifier="i", title="t", description=None)
    assert inv.tables == []


def test_investigation_accepts_tables() -> None:
    table = Table(name="s", source="studies/s/isa.study.xlsx#s", headers=["a"], columns=[["1"]])
    inv = Investigation(identifier="i", title="t", description=None, tables=[table])
    assert inv.tables[0].name == "s"
