"""Wall-clock guard for CPU-bound parse work.

arctrl's ISA parsing is pure Python (Fable-transpiled F#) with no progress hook
and no cancellation. On ARCs with many dense assay worksheets it can run for tens
of minutes inside FsSpreadsheet's RescanRows, which stalls a whole batch run.

SIGALRM is the mechanism that works here: the interpreter checks for pending
signals between bytecodes, so the handler fires even though the call never
releases the GIL and never blocks on I/O.

ParseTimeout is an ordinary Exception on purpose. Deriving it from BaseException
looks tidier (the type would survive arctrl's error wrapping) but deadlocks:
Fable's async trampoline never settles the future it is awaiting, so arctrl's
internal `asyncio.run` blocks forever - a worse failure than the stall this
guards against. Because arctrl re-raises our Exception as a generic "Could not
load ARC" error, callers that need to tell "too slow" apart from "malformed
data" pass a TimeoutState and check `fired`.

Opt-in by design. A slow-but-valid ARC is legitimate data, so the default is no
limit; callers that need a bounded run ask for one. That now includes the
production nightly (deploy/interplant-refresh.service passes --parse-timeout
900), where it is a net against an unknown pathological ARC rather than a
routine cap - the four known ones are excluded by path in harvester/exclusions.py.
"""
from __future__ import annotations

import signal
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

# How often to re-raise once the budget is blown. Small enough that the tail of
# an assay-heavy ARC collapses quickly, large enough to let arctrl unwind between
# interrupts.
_REARM_INTERVAL = 0.2


class ParseTimeout(Exception):
    """Raised when a guarded block exceeds its wall-clock budget."""


@dataclass
class TimeoutState:
    """Records whether the guard fired, since arctrl erases the exception type."""

    fired: bool = False


@contextmanager
def parse_timeout(
    seconds: float | None, *, state: TimeoutState | None = None
) -> Iterator[TimeoutState]:
    """Raise ParseTimeout if the wrapped block runs longer than `seconds`.

    Accepts fractional seconds (setitimer is sub-second capable), which the tests
    rely on to trip a real arctrl parse deterministically.

    `seconds` of None or <= 0 disables the guard entirely. Pass `state` (rather
    than relying on the yielded value) when the caller needs to inspect `fired`
    from an except block, so the name is bound even if setup itself raises.
    Main-thread only: signal.signal rejects other threads, and the harvester's
    batch loop is single-threaded.
    """
    state = state if state is not None else TimeoutState()
    if not seconds or seconds <= 0:
        yield state
        return

    def _on_alarm(signum, frame):  # noqa: ARG001 - signal handler signature
        state.fired = True
        raise ParseTimeout(f"parse exceeded {seconds:g}s budget")

    previous = signal.signal(signal.SIGALRM, _on_alarm)
    # Repeating, not one-shot: arctrl reads each assay as a separate "contract",
    # catching per-contract errors and moving on. A single alarm would only poison
    # one contract and leave the remaining dozens to parse unguarded, so the run
    # would blow the budget anyway. Re-arming keeps interrupting every contract
    # until arctrl gives up and surfaces its aggregated error.
    signal.setitimer(signal.ITIMER_REAL, seconds, _REARM_INTERVAL)
    try:
        yield state
    finally:
        # Clear the timer before restoring the handler so a late alarm cannot
        # fire against the caller's handler.
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
