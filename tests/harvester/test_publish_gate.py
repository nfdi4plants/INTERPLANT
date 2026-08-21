"""The gate between a staged corpus and the public endpoint."""
from __future__ import annotations

import pytest

from harvester import publish


def test_healthy_run_passes():
    r = publish.evaluate(staged_count=144, reported_upserts=144, published_count=144)
    assert r.ok, r.reason
    assert r.kind == publish.KIND_OK
    assert "floor 129" in r.reason and "minimum 120" in r.reason


def test_growth_passes():
    r = publish.evaluate(staged_count=160, reported_upserts=160, published_count=144)
    assert r.ok, r.reason
    assert r.kind == publish.KIND_OK


def test_staged_rows_disagreeing_with_the_report_is_refused():
    r = publish.evaluate(staged_count=140, reported_upserts=144, published_count=144)
    assert not r.ok
    assert r.kind == publish.KIND_MISMATCH


def test_a_collapsed_corpus_is_refused():
    # A night when git.nfdi4plants.org was unreachable for most ARCs.
    r = publish.evaluate(staged_count=20, reported_upserts=20, published_count=144)
    assert not r.ok
    assert r.kind == publish.KIND_FLOOR


def test_the_floor_is_inclusive():
    # 90% of 144 is 129.6, floored to 129.
    ok_result = publish.evaluate(
        staged_count=129, reported_upserts=129, published_count=144
    )
    assert ok_result.ok
    assert ok_result.kind == publish.KIND_OK

    refused_result = publish.evaluate(
        staged_count=128, reported_upserts=128, published_count=144
    )
    assert not refused_result.ok
    assert refused_result.kind == publish.KIND_FLOOR


def test_an_empty_corpus_is_always_refused():
    # First publish: published_count is 0, so the ratio floor is 0 and would
    # pass. Publishing nothing must still be impossible.
    r = publish.evaluate(staged_count=0, reported_upserts=0, published_count=0)
    assert not r.ok
    assert r.kind == publish.KIND_EMPTY


def test_first_publish_of_a_real_corpus_passes():
    r = publish.evaluate(staged_count=144, reported_upserts=144, published_count=0)
    assert r.ok, r.reason
    assert r.kind == publish.KIND_OK


def test_floor_ratio_is_honoured_when_passed_explicitly():
    # Default 0.9 would floor at 129 and refuse; 0.5 floors at 72.
    r = publish.evaluate(
        staged_count=80, reported_upserts=80, published_count=144,
        floor_ratio=0.5, min_records=0,
    )
    assert r.ok, r.reason
    assert r.kind == publish.KIND_OK


def test_an_invalid_floor_ratio_raises_rather_than_failing_open():
    for bad in (0.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="floor_ratio"):
            publish.evaluate(
                staged_count=144, reported_upserts=144, published_count=144,
                floor_ratio=bad,
            )
    with pytest.raises(ValueError, match="min_records"):
        publish.evaluate(
            staged_count=144, reported_upserts=144, published_count=144,
            min_records=-1,
        )


def test_a_ratchet_step_that_clears_the_ratio_is_still_refused():
    # 100 of a published 110 clears the relative floor (int(110*0.9)=99) but is
    # below the absolute minimum. This is the step that, repeated, empties the
    # catalogue with every night reporting success.
    r = publish.evaluate(staged_count=100, reported_upserts=100, published_count=110)
    assert not r.ok
    assert r.kind == publish.KIND_MINIMUM


def test_a_single_record_after_the_table_was_emptied_is_refused():
    # published_count 0 makes the ratio floor 0, so only the absolute minimum
    # stands between a wiped table and publishing one record.
    r = publish.evaluate(staged_count=1, reported_upserts=1, published_count=0)
    assert not r.ok
    assert r.kind == publish.KIND_MINIMUM


def test_min_records_zero_allows_a_deliberately_tiny_corpus():
    r = publish.evaluate(
        staged_count=3, reported_upserts=3, published_count=3, min_records=0
    )
    assert r.ok, r.reason
    assert r.kind == publish.KIND_OK
