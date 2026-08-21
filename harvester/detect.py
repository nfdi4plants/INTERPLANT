"""Compare tonight's GitLab enumeration against the last published one.

This decides WHETHER to harvest, never WHAT to harvest. harvester/dedup.py
resolves mirrored ARCs with a per-run candidate map, so a winner is only correct
when every colliding candidate is seen in the same run; harvesting only the
changed subset would let a DOI-less mirror overwrite a DOI-holding one. The
harvest therefore stays whole-corpus and this module only gates it.

GitLab's last_activity_at bumps on many event types, so this over-triggers
rather than under-triggers, which is the safe direction. The caller's weekly
floor covers anything it misses.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnumerationDiff:
    appeared: tuple[str, ...]
    vanished: tuple[str, ...]
    changed: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not (self.appeared or self.vanished or self.changed)

    def summary(self) -> str:
        return (
            f"{len(self.appeared)} appeared, "
            f"{len(self.vanished)} vanished, "
            f"{len(self.changed)} changed"
        )


def diff_enumeration(live: dict[str, str], published: dict[str, str]) -> EnumerationDiff:
    """Diff project_path -> last_activity_at maps. Sorted, so logs are stable."""
    live_paths = set(live)
    published_paths = set(published)
    return EnumerationDiff(
        appeared=tuple(sorted(live_paths - published_paths)),
        vanished=tuple(sorted(published_paths - live_paths)),
        changed=tuple(
            sorted(
                p for p in live_paths & published_paths if live[p] != published[p]
            )
        ),
    )
