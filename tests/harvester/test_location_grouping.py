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
    # REGRESSION (permanent guard, single-group shape): Teosinte's POBL is
    # row-unique (3604 of 3604). Grouping label-first on it produced 3604
    # points instead of 276. This table has exactly ONE coordinate group, so
    # ACCESION is constant across every row by construction - the common
    # single-field-trial shape - and must still be used as the label: a
    # constant column is only rejected when there is more than one point to
    # discriminate between (see _label_candidates).
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


def test_table_wide_constant_label_column_loses_to_a_varying_one() -> None:
    # Teosinte carries Parameter [Species]: 2-3 values shared across all 3604
    # rows and constant within any single site, preceding ESTADO/ACCESION in
    # header order. Unchecked, it would win as the label for every point
    # instead of the column that actually names the site.
    table = _table(
        ["Parameter [Species]", "Parameter [ESTADO]", "Parameter [latitude]",
         "Parameter [longitude]"],
        [
            ["Zea mays", "Zea mays", "Zea mays", "Zea mays"],  # table-wide constant
            ["Oaxaca", "Oaxaca", "Oaxaca", "Jalisco"],
            ["18.485833", "18.485833", "18.485833", "20.0"],
            ["-99.791667", "-99.791667", "-99.791667", "-100.0"],
        ],
    )
    points = points_from_tables([table], curated_role=None)
    assert len(points) == 2
    site = next(p for p in points if p["n_rows"] == 3)
    assert site["label"] == "Oaxaca"
    assert site["label_field"] == "ESTADO"


def test_a_sparse_label_column_is_not_treated_as_row_unique() -> None:
    # REGRESSION: row-uniqueness must compare against the table's row count,
    # not the non-blank cell count. A sparse column with all-distinct
    # non-blank values (2 distinct values in 2 non-blank cells out of 5 rows)
    # used to be rejected as if it were a per-row identifier.
    table = _table(
        ["Parameter [SITE]", "Parameter [latitude]", "Parameter [longitude]"],
        [
            ["Site-A", "Site-B", None, None, None],
            ["18.485833", "20.0", "18.485833", "20.0", "18.485833"],
            ["-99.791667", "-100.0", "-99.791667", "-100.0", "-99.791667"],
        ],
    )
    points = points_from_tables([table], curated_role=None)
    site_a = next(p for p in points if p["n_rows"] == 3)
    assert site_a["label"] == "Site-A"
    assert site_a["label_field"] == "SITE"


def test_generic_tier_label_field_is_bare_like_the_specific_tier() -> None:
    # unwrap_header does not strip "Input [...]" (only Parameter/
    # Characteristic/Factor/Comment/Component), so the generic tier needs its
    # own bare-name mapping to match the specific tier's shape (e.g.
    # "ACCESION", not "Parameter [ACCESION]").
    table = _table(
        ["Input [Source Name]", "Parameter [latitude]", "Parameter [longitude]"],
        [
            ["SRC-1", "SRC-1", "SRC-1", "SRC-2"],
            ["18.485833", "18.485833", "18.485833", "20.0"],
            ["-99.791667", "-99.791667", "-99.791667", "-100.0"],
        ],
    )
    points = points_from_tables([table], curated_role=None)
    site = next(p for p in points if p["n_rows"] == 3)
    assert site["label"] == "SRC-1"
    assert site["label_field"] == "Source Name"


def test_a_row_with_only_one_axis_parseable_is_dropped_entirely() -> None:
    # The existing unparseable-rows test makes both axes fail together; this
    # exercises the half-parsed path, where one axis is fine and the other is
    # not within the same row.
    table = _table(
        ["Parameter [latitude]", "Parameter [longitude]"],
        [["18.485833", "20.0"], ["not-a-number", "-100.0"]],
    )
    points = points_from_tables([table], curated_role=None)
    assert len(points) == 1
    assert points[0]["point"] == [-100.0, 20.0]


def test_a_duplicate_axis_column_keeps_the_first_and_logs_the_discard(caplog) -> None:
    table = _table(
        ["Parameter [latitude]", "Parameter [latitude]", "Parameter [longitude]"],
        [["18.485833"], ["99.0"], ["-99.791667"]],
    )
    with caplog.at_level("WARNING"):
        points = points_from_tables([table], curated_role=None)
    assert len(points) == 1
    assert points[0]["point"] == [-99.791667, 18.485833]  # first latitude column wins
    assert "Duplicate lat column" in caplog.text


def test_multiple_tables_are_combined_and_sorted_across_tables() -> None:
    table_a = _table(
        ["Parameter [Material source latitude]", "Parameter [Material source longitude]"],
        [["48.0"], ["11.0"]],
        name="sheet_a",
    )
    table_b = _table(
        ["Parameter [Biological material latitude]", "Parameter [Biological material longitude]"],
        [["6.0"], ["51.0"]],
        name="sheet_b",
    )
    points = points_from_tables([table_a, table_b], curated_role=None)
    assert len(points) == 2
    assert points[0]["role"] == "material-origin"
    assert points[0]["point"] == [51.0, 6.0]
    assert points[1]["role"] == "material-source"
    assert points[1]["point"] == [11.0, 48.0]


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


def test_hemisphere_confirmed_swapped_columns_are_corrected(caplog) -> None:
    # Measured on usadellab/quinoa_chileanfieldtrial: the "latitude" column
    # holds '70°47′ W' and the "longitude" column holds '28°34′ S'. parse_coord
    # rejects both in the declared orientation (hemisphere contradicts axis),
    # but each parses cleanly on the OTHER axis, and the hemisphere letters
    # confirm the swap rather than merely permitting it numerically.
    table = _table(
        [
            "Characteristic [Geographic location (latitude)]",
            "Characteristic [Geographic location (longitude)]",
        ],
        [["70°47′ W"], ["28°34′ S"]],
    )
    with caplog.at_level("WARNING"):
        points = points_from_tables([table], curated_role=None)
    assert len(points) == 1
    assert points[0]["role"] == "experiment-site"
    assert points[0]["point"] == [-70.783333, -28.566667]
    assert "Swapped lat/lon columns" in caplog.text


def test_a_bare_number_pair_that_fits_either_orientation_is_not_swapped() -> None:
    # The declared "latitude" value (120.0) is out of range so the declared
    # orientation yields zero pairs, and the swapped orientation happens to be
    # numerically plausible (120.0 is a valid longitude, 45.0 a valid
    # latitude) - but neither raw value carries a hemisphere letter, so this
    # must NOT be treated as a swap. A bare number pair is not evidence.
    table = _table(
        ["Parameter [latitude]", "Parameter [longitude]"],
        [["120.0"], ["45.0"]],
    )
    points = points_from_tables([table], curated_role=None)
    assert points == []


def test_declared_orientation_wins_when_it_yields_any_pair_even_with_bad_rows() -> None:
    # Row 0 parses fine in the declared orientation. Row 1's "latitude" cell
    # (999) is unparseable on any axis. Because the declared orientation
    # already yields a pair, swap detection must never run - row 1 is simply
    # dropped, not reinterpreted.
    table = _table(
        ["Parameter [latitude]", "Parameter [longitude]"],
        [["18.485833", "999"], ["-99.791667", "-99.791667"]],
    )
    points = points_from_tables([table], curated_role=None)
    assert len(points) == 1
    assert points[0]["point"] == [-99.791667, 18.485833]
    assert points[0]["n_rows"] == 1


def test_points_are_ordered_deterministically() -> None:
    table = _table(
        ["Parameter [latitude]", "Parameter [longitude]"],
        [["20.0", "18.0", "19.0"], ["-100.0", "-99.0", "-98.0"]],
    )
    first = points_from_tables([table], curated_role=None)
    second = points_from_tables([table], curated_role=None)
    assert first == second
    assert [p["point"] for p in first] == sorted(p["point"] for p in first)
