"""The gate between a staged corpus and the public endpoint."""
from __future__ import annotations

from harvester import publish


def test_healthy_run_passes():
    r = publish.evaluate(staged_count=144, reported_upserts=144, published_count=144)
    assert r.ok, r.reason


def test_growth_passes():
    r = publish.evaluate(staged_count=160, reported_upserts=160, published_count=144)
    assert r.ok, r.reason


def test_staged_rows_disagreeing_with_the_report_is_refused():
    r = publish.evaluate(staged_count=140, reported_upserts=144, published_count=144)
    assert not r.ok
    assert "140" in r.reason and "144" in r.reason


def test_a_collapsed_corpus_is_refused():
    # A night when git.nfdi4plants.org was unreachable for most ARCs.
    r = publish.evaluate(staged_count=20, reported_upserts=20, published_count=144)
    assert not r.ok
    assert "floor" in r.reason


def test_the_floor_is_inclusive():
    # 90% of 144 is 129.6, floored to 129.
    assert publish.evaluate(
        staged_count=129, reported_upserts=129, published_count=144
    ).ok
    assert not publish.evaluate(
        staged_count=128, reported_upserts=128, published_count=144
    ).ok


def test_an_empty_corpus_is_always_refused():
    # First publish: published_count is 0, so the ratio floor is 0 and would
    # pass. Publishing nothing must still be impossible.
    r = publish.evaluate(staged_count=0, reported_upserts=0, published_count=0)
    assert not r.ok
    assert "empty" in r.reason


def test_first_publish_of_a_real_corpus_passes():
    r = publish.evaluate(staged_count=144, reported_upserts=144, published_count=0)
    assert r.ok, r.reason
