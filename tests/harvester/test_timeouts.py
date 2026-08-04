"""Unit tests for the CPU-bound parse guard."""
from __future__ import annotations

import signal
import time

import pytest

from harvester.timeouts import ParseTimeout, parse_timeout


def _busy_loop(seconds: float) -> None:
    """Spin without sleeping, so only a signal can interrupt us."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        pass


@pytest.mark.parametrize("disabled", [None, 0])
def test_disabled_guard_lets_the_block_finish(disabled):
    with parse_timeout(disabled):
        result = "done"
    assert result == "done"


def test_cpu_bound_overrun_raises_parse_timeout():
    """The whole point: interrupt work that never blocks and never yields."""
    start = time.monotonic()
    with pytest.raises(ParseTimeout, match="exceeded 1s"), parse_timeout(1):
        _busy_loop(30)
    assert time.monotonic() - start < 10  # fired on the alarm, not after 30s


def test_block_under_budget_is_not_interrupted():
    with parse_timeout(10):
        _busy_loop(0.05)


def test_timer_and_handler_are_restored_after_success():
    sentinel = signal.getsignal(signal.SIGALRM)
    with parse_timeout(10):
        pass
    assert signal.getsignal(signal.SIGALRM) is sentinel
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_timer_and_handler_are_restored_after_timeout():
    sentinel = signal.getsignal(signal.SIGALRM)
    with pytest.raises(ParseTimeout), parse_timeout(1):
        _busy_loop(30)
    assert signal.getsignal(signal.SIGALRM) is sentinel
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_guard_rearms_so_a_swallowed_interrupt_is_retried():
    """arctrl catches per-contract errors and continues; one alarm is not enough.

    Without a repeating interval the budget silently fails to bound assay-heavy
    ARCs, which is the exact stall this module exists to prevent.
    """
    with parse_timeout(5):
        _, interval = signal.getitimer(signal.ITIMER_REAL)
    assert interval > 0


def test_overrun_still_terminates_when_the_first_interrupts_are_swallowed():
    """Simulate arctrl: swallow ParseTimeout per unit of work, keep going."""
    units, unit_seconds = 20, 2.0  # 40s of work if nothing interrupts it
    attempts = 0

    def swallowing_work():
        nonlocal attempts
        for _ in range(units):
            attempts += 1
            try:
                _busy_loop(unit_seconds)
            except ParseTimeout:
                continue  # what arctrl does per contract

    start = time.monotonic()
    with parse_timeout(1):
        swallowing_work()
    elapsed = time.monotonic() - start
    # Each unit past the budget dies within the re-arm interval, so the tail
    # collapses to roughly interval * units rather than running the full 40s.
    assert attempts == units
    assert elapsed < units * unit_seconds / 2


def test_no_stray_alarm_after_the_block_exits():
    """A leaked timer would kill an unrelated later stage of the same run."""
    with parse_timeout(1):
        pass
    _busy_loop(1.5)  # would raise here if the itimer were still armed
