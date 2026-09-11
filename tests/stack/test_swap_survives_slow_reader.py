"""A slow pygeoapi query must not abort the nightly publish.

harvester/publish.py wraps TRUNCATE public.records in lock_timeout = '5s'. A
reader holding ACCESS SHARE past that window makes the swap fail, the corpus
goes stale, and AWI's 5-day TTL starts ageing real records out of the portal.
The pygeoapi role's statement_timeout (3s) is what prevents it.

Measured 2026-09-11 before the fix existed: a 12s reader with no timeout
BLOCKED the swap after 5.0s with LockNotAvailable. With statement_timeout=3s
the swap SUCCEEDED after 2.0s and the reader was the thing that died.

Everything runs in transactions that roll back, so the dev corpus survives.
"""
from __future__ import annotations

import threading
import time

import psycopg
import pytest

pytestmark = pytest.mark.db

_PASSWORD = "test-ro-password"
_RO_DSN = f"host=localhost port=5432 dbname=interplant user=pygeoapi_ro password={_PASSWORD}"


@pytest.fixture
def role_ready(pg_dsn: str):
    from harvester import db

    with psycopg.connect(pg_dsn, autocommit=True) as admin:
        db.apply_schema(admin)
        db.apply_catalog_views(admin)
        db.apply_pygeoapi_role(admin, password=_PASSWORD)
    yield


def _hold_a_slow_read(seconds: float, outcome: dict) -> threading.Thread:
    def run() -> None:
        try:
            with psycopg.connect(_RO_DSN) as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT count(*), pg_sleep(%s) FROM public.arc_locations",
                            (seconds,),
                        )
                        cur.fetchall()
                    raise psycopg.Rollback
        except Exception as exc:  # noqa: BLE001 - the type IS the assertion
            outcome["reader"] = type(exc).__name__
        else:
            outcome["reader"] = "completed"

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def _hold_an_idle_transaction(seconds: float, outcome: dict) -> threading.Thread:
    def run() -> None:
        try:
            with psycopg.connect(_RO_DSN) as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute("SELECT count(*) FROM public.arc_locations")
                        cur.fetchall()
                    time.sleep(seconds)
                    raise psycopg.Rollback
        except Exception as exc:  # noqa: BLE001 - the type IS the assertion
            outcome["reader"] = type(exc).__name__
        else:
            outcome["reader"] = "completed"

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def test_the_swap_wins_against_a_slow_reader(role_ready, pg_dsn: str) -> None:
    outcome: dict[str, str] = {}
    reader = _hold_a_slow_read(12, outcome)
    time.sleep(1)  # let the reader take ACCESS SHARE first

    started = time.perf_counter()
    swap_error = None
    try:
        with psycopg.connect(pg_dsn) as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    # Exactly what harvester/publish.py does.
                    cur.execute("SET LOCAL lock_timeout = '5s'")
                    cur.execute("TRUNCATE public.records")
                raise psycopg.Rollback
    except psycopg.Rollback:
        pass
    except Exception as exc:  # noqa: BLE001
        swap_error = exc
    elapsed = time.perf_counter() - started
    reader.join()

    assert swap_error is None, f"swap was blocked by the reader: {swap_error}"
    assert elapsed < 5, f"swap waited {elapsed:.1f}s, too close to the 5s lock_timeout"
    assert outcome["reader"] == "QueryCanceled", (
        f"expected the reader to be cancelled by statement_timeout, got {outcome['reader']!r} - "
        "if this says 'completed', the pygeoapi role has no statement_timeout and the "
        "nightly publish is at risk"
    )


def test_the_swap_wins_against_an_idle_in_transaction_reader(role_ready, pg_dsn: str) -> None:
    outcome: dict[str, str] = {}
    reader = _hold_an_idle_transaction(12, outcome)
    time.sleep(1)  # let the reader take ACCESS SHARE first

    started = time.perf_counter()
    swap_error = None
    try:
        with psycopg.connect(pg_dsn) as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    # Exactly what harvester/publish.py does.
                    cur.execute("SET LOCAL lock_timeout = '5s'")
                    cur.execute("TRUNCATE public.records")
                raise psycopg.Rollback
    except psycopg.Rollback:
        pass
    except Exception as exc:  # noqa: BLE001
        swap_error = exc
    elapsed = time.perf_counter() - started
    reader.join()

    assert swap_error is None, f"swap was blocked by the idle reader: {swap_error}"
    assert elapsed < 5, f"swap waited {elapsed:.1f}s, too close to the 5s lock_timeout"
    assert outcome["reader"] == "Rollback", (
        f"expected the idle-in-transaction reader to be terminated by the server, "
        f"got {outcome['reader']!r} - "
        "if this says 'completed', the pygeoapi role has no "
        "idle_in_transaction_session_timeout and the nightly publish is at risk. "
        "psycopg surfaces the termination as Rollback: when idle_in_transaction "
        "kills the session, the explicit rollback fails and psycopg re-raises the "
        "block's Rollback exception (log: 'terminating connection due to "
        "idle-in-transaction timeout')."
    )