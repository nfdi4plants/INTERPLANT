"""Tests for the public.arc_locations view. Requires a running Postgres.

The `seeded_locations` fixture lives in tests/stack/conftest.py because Task 12
uses it too, and pytest cannot share a fixture across modules otherwise. It
connects via the existing `pg_dsn` fixture, matching the pattern in
tests/stack/test_catalog_api.py. There is no shared `db_cursor` fixture in
conftest.py; do not invent one.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.db


def _rows(conn, sql: str, params: tuple) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def test_arc_locations_explodes_one_row_per_point(seeded_locations) -> None:
    rows = _rows(
        seeded_locations,
        "SELECT count(*) FROM public.arc_locations WHERE record_id = %s",
        ("dataplant-multi",),
    )
    assert rows[0][0] == 3


def test_arc_locations_carries_role_and_precision(seeded_locations) -> None:
    rows = _rows(
        seeded_locations,
        "SELECT role, precision, n_rows FROM public.arc_locations "
        "WHERE record_id = %s ORDER BY role, n_rows",
        ("dataplant-multi",),
    )
    assert rows[0][0] == "collection-site"
    assert rows[0][1] == "exact"


def test_arc_locations_geom_is_a_point_in_4326(seeded_locations) -> None:
    rows = _rows(
        seeded_locations,
        "SELECT ST_GeometryType(geom), ST_SRID(geom) FROM public.arc_locations "
        "WHERE record_id = %s LIMIT 1",
        ("dataplant-multi",),
    )
    assert rows[0][0] == "ST_Point"
    assert rows[0][1] == 4326


def test_a_record_with_no_locations_contributes_no_rows(seeded_locations) -> None:
    rows = _rows(
        seeded_locations,
        "SELECT count(*) FROM public.arc_locations WHERE record_id = %s",
        ("dataplant-empty",),
    )
    assert rows[0][0] == 0


def test_axis_order_survives_the_view(seeded_locations) -> None:
    # payload point is [lon, lat] per GeoJSON; ST_X is longitude.
    rows = _rows(
        seeded_locations,
        "SELECT ST_X(geom), ST_Y(geom) FROM public.arc_locations "
        "WHERE record_id = %s AND role = %s",
        ("dataplant-multi", "custodian-institution"),
    )
    lon, lat = rows[0]
    assert lon == pytest.approx(6.7926)
    assert lat == pytest.approx(51.1889)