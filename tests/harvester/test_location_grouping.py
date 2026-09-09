"""Tests for grouping ISA rows into deduplicated, labelled points."""
from __future__ import annotations

from harvester.extractors.location import points_from_tables
from harvester.isa_reader import Table


def _table(headers: list[str], columns: list[list[str | None]], name: str = "sheet1") -> Table:
    return Table(
        name=name,
        source=f"studies/s/isa.study.xlsx#{name}",
        headers=headers,
        columns=columns,
    )


def test_identical_coordinates_collapse_to_one_point_with_a_row_count() -> None:
    table = _table(
        ["Parameter [latitude]", "Parameter [longitude]"],
        [["18.485833", "18.485833", "18.485833"], ["-99.791667", "-99.791667", "-99.791667"]],
    )
    points = points_from_tables([table], curated_role=None)
    assert len(points) == 1
    assert points[0]["point"] == [-99.791667, 18.485833]  # GeoJSON order: lon, lat
    assert points[0]["n_rows"] == 3


def test_distinct_coordinates_yield_distinct_points() -> None:
    table = _table(
        ["Parameter [latitude]", "Parameter [longitude]"],
        [["18.485833", "20.0"], ["-99.791667", "-100.0"]],
    )
    points = points_from_tables([table], curated_role=None)
    assert len(points) == 2


def test_a_row_unique_label_column_does_not_inflate_the_point_count() -> None:
    # REGRESSION: Teosinte's POBL is row-unique (3604 of 3604). Grouping
    # label-first on it produced 3604 points instead of 276.
    table = _table(
        ["Parameter [POBL]", "Parameter [ACCESION]", "Parameter [latitude]",
         "Parameter [longitude]"],
        [
            ["BIXC_100_10", "BIXC_100_11", "BIXC_100_12"],   # row-unique: rejected
            ["ACC-1", "ACC-1", "ACC-1"],                      # constant: usable label
            ["18.485833", "18.485833", "18.485833"],
            ["-99.791667", "-99.791667", "-99.791667"],
        ],
    )
    points = points_from_tables([table], curated_role=None)
    assert len(points) == 1
    assert points[0]["n_rows"] == 3
    assert points[0]["label"] == "ACC-1"
    assert points[0]["label_field"] == "ACCESION"


def test_label_is_null_when_no_candidate_qualifies() -> None:
    table = _table(
        ["Parameter [latitude]", "Parameter [longitude]"],
        [["18.485833"], ["-99.791667"]],
    )
    points = points_from_tables([table], curated_role=None)
    assert points[0]["label"] is None
    assert points[0]["label_field"] is None


def test_header_declared_role_wins_over_the_curated_role() -> None:
    table = _table(
        ["Parameter [Biological material latitude]", "Parameter [Biological material longitude]"],
        [["51.0"], ["6.0"]],
    )
    points = points_from_tables([table], curated_role="experiment-site")
    assert points[0]["role"] == "material-origin"


def test_curated_role_applies_to_ad_hoc_headers() -> None:
    table = _table(
        ["Parameter [latitude]", "Parameter [longitude]"],
        [["51.0"], ["6.0"]],
    )
    points = points_from_tables([table], curated_role="collection-site")
    assert points[0]["role"] == "collection-site"


def test_unlisted_ad_hoc_headers_are_unspecified_never_guessed() -> None:
    table = _table(
        ["Parameter [latitude]", "Parameter [longitude]"],
        [["51.0"], ["6.0"]],
    )
    points = points_from_tables([table], curated_role=None)
    assert points[0]["role"] == "unspecified"


def test_two_roles_in_one_table_stay_separate() -> None:
    # shape/shape, bridge-core50 and Curated_wheat each carry material-origin
    # and material-source filled at the same time.
    table = _table(
        [
            "Parameter [Biological material latitude]",
            "Parameter [Biological material longitude]",
            "Parameter [Material source latitude]",
            "Parameter [Material source longitude]",
        ],
        [["51.0"], ["6.0"], ["48.0"], ["11.0"]],
    )
    points = points_from_tables([table], curated_role=None)
    roles = {p["role"] for p in points}
    assert roles == {"material-origin", "material-source"}


def test_coordinates_in_an_assay_table_are_extracted() -> None:
    # flyover_redacted and dormancy_NhuTran_2025 keep coordinates only here.
    table = Table(
        name="flyover_2025_02",
        source="assays/drone_image_capture/isa.assay.xlsx#flyover_2025_02",
        headers=["Parameter [Latitude]", "Parameter [Longitude]"],
        columns=[["+49.42608333"], ["+7.75402778"]],
    )
    points = points_from_tables([table], curated_role="experiment-site")
    assert len(points) == 1
    assert points[0]["source"].startswith("assays/")
    assert points[0]["precision"] == "exact"


def test_unparseable_rows_are_skipped_without_raising() -> None:
    table = _table(
        ["Parameter [latitude]", "Parameter [longitude]"],
        [
            ["./studies/Organisms/protocols/ArabidopsisGrowth.md", "18.485833"],
            ["./studies/Organisms/protocols/ArabidopsisGrowth.md", "-99.791667"],
        ],
    )
    points = points_from_tables([table], curated_role=None)
    assert len(points) == 1


def test_a_table_with_only_one_axis_yields_nothing() -> None:
    table = _table(["Parameter [latitude]"], [["18.485833"]])
    assert points_from_tables([table], curated_role=None) == []


def test_points_are_ordered_deterministically() -> None:
    table = _table(
        ["Parameter [latitude]", "Parameter [longitude]"],
        [["20.0", "18.0", "19.0"], ["-100.0", "-99.0", "-98.0"]],
    )
    first = points_from_tables([table], curated_role=None)
    second = points_from_tables([table], curated_role=None)
    assert first == second
    assert [p["point"] for p in first] == sorted(p["point"] for p in first)
