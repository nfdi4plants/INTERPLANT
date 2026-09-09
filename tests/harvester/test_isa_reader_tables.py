"""Tests for the Table dataclass and Investigation.tables."""
from __future__ import annotations

from pathlib import Path

from harvester.isa_reader import Investigation, IsaReader, Table

# Same committed fixture tests/harvester/test_isa_reader.py reads, with no
# skip/gate: it ships in the repo so IsaReader can always be exercised for real.
FIXTURE = Path(__file__).parent.parent / "fixtures" / "arcs" / "ArcPrototype"


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


def test_reader_collects_tables_from_both_studies_and_assays() -> None:
    """Pins the both-directories requirement and real header/column parallelism.

    Count equality alone would still pass for a reversed column list, so this
    also locates a known header by value and checks its matching column by
    value - that is the assertion that actually pins parallelism.
    """
    investigation = IsaReader().read(FIXTURE)
    tables = investigation.tables

    assert any(t.source.startswith("studies/") for t in tables)
    assert any(t.source.startswith("assays/") for t in tables)

    for table in tables:
        assert len(table.headers) == len(table.columns)

    cell_cultivation = next(
        t for t in tables if t.source.endswith("#CellCultivation")
    )
    organism_index = cell_cultivation.headers.index("Characteristic [organism]")
    assert "Arabidopsis thaliana" in cell_cultivation.columns[organism_index]
