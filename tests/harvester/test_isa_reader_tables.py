"""Tests for the Table dataclass and Investigation.tables."""
from __future__ import annotations

from pathlib import Path

from harvester.isa_reader import Investigation, IsaReader, Table, _cell_text

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


# _cell_text: the value-extraction helper _tables_of's column loop uses instead
# of _annotation_name, so a unitized coordinate cell (flyover_redacted) yields
# its bare value instead of "<value> <unit>".


class _FakeUnitizedCell:
    """Stands in for an arctrl CompositeCell with is_unitized=True.

    Real shape measured on agdafair/flyover_redacted: str(cell) ==
    '+7.75402778 degree', cell.GetContent() ==
    ['+7.75402778', 'degree', '<UO term uri>', '<UO term uri>'].
    """

    is_unitized = True

    def __init__(self, content):
        self._content = content

    def __str__(self) -> str:
        return "+7.75402778 degree"

    def GetContent(self):
        return self._content


class _FakeUnitizedCellRaising:
    is_unitized = True

    def __str__(self) -> str:
        return "fallback text"

    def GetContent(self):
        raise RuntimeError("unexpected GetContent shape")


class _FakeUnitizedCellEmptyContent:
    is_unitized = True

    def __str__(self) -> str:
        return "fallback text"

    def GetContent(self):
        return []


class _FakeOntologyAnnotation:
    Name = "Arabidopsis thaliana"

    def __str__(self) -> str:
        return "{Name = Arabidopsis thaliana; TSR = ...; TAN = ...}"


def test_cell_text_returns_the_bare_value_of_a_unitized_cell() -> None:
    cell = _FakeUnitizedCell(
        ["+7.75402778", "degree", "http://purl.obolibrary.org/obo/UO_0000185"]
    )
    assert _cell_text(cell) == "+7.75402778"


def test_cell_text_passes_plain_strings_through_unchanged() -> None:
    assert _cell_text("Arabidopsis thaliana") == "Arabidopsis thaliana"


def test_cell_text_still_extracts_name_from_an_ontology_annotation() -> None:
    assert _cell_text(_FakeOntologyAnnotation()) == "Arabidopsis thaliana"


def test_cell_text_falls_back_to_str_when_get_content_raises() -> None:
    assert _cell_text(_FakeUnitizedCellRaising()) == "fallback text"


def test_cell_text_falls_back_to_str_when_get_content_is_empty() -> None:
    assert _cell_text(_FakeUnitizedCellEmptyContent()) == "fallback text"
