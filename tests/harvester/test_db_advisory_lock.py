"""The advisory lock serializing concurrent refresh runs (real Postgres)."""
from __future__ import annotations

import pytest

from harvester import db


@pytest.mark.db
def test_a_second_connection_cannot_acquire_a_held_lock(pg_dsn):
    conn_a = db.connect(pg_dsn)
    conn_b = db.connect(pg_dsn)
    try:
        assert db.try_advisory_lock(conn_a) is True
        assert db.try_advisory_lock(conn_b) is False
    finally:
        conn_a.close()
        conn_b.close()


@pytest.mark.db
def test_closing_the_holding_connection_releases_the_lock(pg_dsn):
    conn_a = db.connect(pg_dsn)
    assert db.try_advisory_lock(conn_a) is True
    conn_a.close()  # session-level lock must not survive the session

    conn_b = db.connect(pg_dsn)
    try:
        assert db.try_advisory_lock(conn_b) is True
    finally:
        conn_b.close()
