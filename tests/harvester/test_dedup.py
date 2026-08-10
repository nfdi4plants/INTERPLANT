"""Collision resolution: which of two ARCs claiming one record id wins."""
from __future__ import annotations

import itertools

from harvester import dedup


def _cand(**kw) -> dedup.Candidate:
    base = dict(
        record_id="dataplant-tga-basu26",
        title="TGA Basu 26",
        has_doi=False,
        last_activity_at="2026-01-01T00:00:00Z",
        namespace="sbasu1",
        unique_id="abcdef01-2345-6789-abcd-ef0123456789",
    )
    base.update(kw)
    return dedup.Candidate(**base)


def test_doi_beats_no_doi_regardless_of_recency():
    older_with_doi = _cand(has_doi=True, last_activity_at="2020-01-01T00:00:00Z")
    newer_without = _cand(has_doi=False, last_activity_at="2026-07-01T00:00:00Z",
                          namespace="ceplas")
    assert dedup.prefer(older_with_doi, newer_without) is True
    assert dedup.prefer(newer_without, older_with_doi) is False


def test_recency_decides_when_doi_status_matches():
    newer = _cand(last_activity_at="2026-07-01T00:00:00Z", namespace="ceplas")
    older = _cand(last_activity_at="2024-01-01T00:00:00Z", namespace="sbasu1")
    assert dedup.prefer(newer, older) is True
    assert dedup.prefer(older, newer) is False


def test_lexicographically_first_namespace_wins_the_final_tiebreak():
    first = _cand(namespace="ceplas")
    later = _cand(namespace="sbasu1")
    assert dedup.prefer(first, later) is True
    assert dedup.prefer(later, first) is False


def test_prefer_falls_back_to_unique_id_when_namespace_and_recency_tie():
    """Namespace is not unique per ARC: two repos in one namespace can share it.

    Two ARCs in the same namespace with the same recency and DOI status must
    still resolve to a total order, so the final tiebreak has to reach past
    namespace to unique_id (a uuid5 over the ARC source uri, genuinely unique
    per ARC).
    """
    lower = _cand(unique_id="00000000-0000-0000-0000-000000000001")
    higher = _cand(unique_id="00000000-0000-0000-0000-000000000002")
    assert dedup.prefer(lower, higher) is True
    assert dedup.prefer(higher, lower) is False


def test_prefer_is_order_independent_over_every_pair():
    """The property that matters: the winner never depends on arrival order."""
    candidates = [
        _cand(has_doi=True, last_activity_at="2026-01-01T00:00:00Z", namespace="ceplas"),
        _cand(has_doi=False, last_activity_at="2026-07-01T00:00:00Z", namespace="sbasu1"),
        _cand(has_doi=False, last_activity_at="2026-07-01T00:00:00Z", namespace="usadellab"),
        _cand(has_doi=True, last_activity_at="2019-05-05T00:00:00Z", namespace="madland"),
    ]
    for a, b in itertools.permutations(candidates, 2):
        assert dedup.prefer(a, b) != dedup.prefer(b, a), (a.namespace, b.namespace)


def test_namespace_of_strips_the_repository_segment():
    assert dedup.namespace_of("https://git.nfdi4plants.org/ceplas/TGA_Basu26") == "ceplas"
    assert dedup.namespace_of(
        "https://git.nfdi4plants.org/hhu_molphys_frommer/published/Kaplunova_2025_TPJ"
    ) == "hhu_molphys_frommer/published"


def test_candidate_from_record_reads_doi_title_and_unique_id():
    record = {
        "id": "dataplant-x",
        "properties": {
            "title": "A Real Study",
            "uniqueId": "abcdef01-2345-6789-abcd-ef0123456789",
            "arc_source_uri": "https://git.nfdi4plants.org/ceplas/X",
            "publications": [{"title": "no doi here"}, {"title": "p", "doi": "10.1234/x"}],
        },
    }
    cand = dedup.candidate_from_record(record, last_activity_at="2026-02-02T00:00:00Z")
    assert cand.record_id == "dataplant-x"
    assert cand.title == "A Real Study"
    assert cand.has_doi is True
    assert cand.namespace == "ceplas"
    assert cand.last_activity_at == "2026-02-02T00:00:00Z"
    assert cand.unique_id == "abcdef01-2345-6789-abcd-ef0123456789"


def test_candidate_has_no_doi_when_no_publication_carries_one():
    record = {
        "id": "dataplant-x",
        "properties": {
            "title": "T",
            "uniqueId": "abcdef01-2345-6789-abcd-ef0123456789",
            "arc_source_uri": "https://git.nfdi4plants.org/ceplas/X",
            "publications": [{"title": "no doi here"}],
        },
    }
    assert dedup.candidate_from_record(record, last_activity_at="").has_doi is False
