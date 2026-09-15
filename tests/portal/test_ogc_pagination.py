"""The paging loop, and the rules that make this reader safe to point at a
server we did not write. Reachable offline: their fetch only special-cases
file:// URLs, so an http stub exercises the real code path."""
from __future__ import annotations

from itertools import islice
from urllib.parse import parse_qs, urlparse

import pytest

from tests.portal.stub_ogc_server import StubOGC


def _harvester(module, url, tmp_path, collections=("c",)):
    return module.OGCAPIRecordsHarvester(
        url=url, collections=list(collections), page_size=10,
        logfile=str(tmp_path / "h.log"),
    )


def test_follows_rel_next_until_exhausted(ogc_helper_module, tmp_path):
    with StubOGC(total=25, mode="next") as stub:
        ids = [f["id"] for f in _harvester(ogc_helper_module, stub.base, tmp_path).iter_items("c")]
    assert len(ids) == 25
    assert len(set(ids)) == 25, "a page was repeated"


def test_falls_back_to_offset_when_there_is_no_next_link(ogc_helper_module, tmp_path):
    with StubOGC(total=25, mode="offset_only") as stub:
        ids = [f["id"] for f in _harvester(ogc_helper_module, stub.base, tmp_path).iter_items("c")]
    assert len(ids) == 25


def test_without_next_or_numberMatched_it_stops_after_one_page(ogc_helper_module, tmp_path):
    with StubOGC(total=25, mode="offset_only") as stub:
        stub.omit_number_matched = True
        ids = [f["id"] for f in _harvester(ogc_helper_module, stub.base, tmp_path).iter_items("c")]
    assert len(ids) == 10


def test_a_next_link_that_does_not_advance_stops_the_loop(ogc_helper_module, tmp_path):
    with StubOGC(total=25, mode="stuck_next") as stub:
        with pytest.raises(RuntimeError, match="did not advance"):
            list(_harvester(ogc_helper_module, stub.base, tmp_path).iter_items("c"))


def test_a_server_that_ignores_offset_and_sends_no_next_is_caught(ogc_helper_module, tmp_path):
    """No rel=next and an ignored offset: the URL keeps changing (our own
    fallback increments it), so the URL-repeat guard never fires, but every
    page is really the same 10 records. Left unguarded this yields 30 items
    for 10 unique ids and returns normally - a silent partial harvest that
    the docstring promises never happens."""
    with StubOGC(total=25, page_size=10, mode="ignores_offset") as stub:
        with pytest.raises(RuntimeError, match="did not advance"):
            list(_harvester(ogc_helper_module, stub.base, tmp_path).iter_items("c"))


def test_a_rotating_next_link_that_never_moves_is_caught(ogc_helper_module, tmp_path):
    """The next link's URL changes every time (defeating the URL-repeat guard)
    but always resolves to the same page. Capped at 100 items so a run against
    unfixed code fails fast instead of hanging."""
    with StubOGC(total=25, page_size=10, mode="rotating_next") as stub:
        with pytest.raises(RuntimeError, match="did not advance"):
            list(islice(_harvester(ogc_helper_module, stub.base, tmp_path).iter_items("c"), 100))


def test_overlapping_pages_are_deduplicated_not_yielded_twice(ogc_helper_module, tmp_path):
    """Each page rewinds 5 items, so every page carries new ids and the
    no-new-id guard never fires. Counting the repeats as progress would end
    the harvest early; the records must instead be delivered once each."""
    with StubOGC(total=25, page_size=10, mode="overlapping", overlap=5) as stub:
        ids = [f["id"] for f in islice(
            _harvester(ogc_helper_module, stub.base, tmp_path).iter_items("c"), 200)]
    assert len(ids) == 25, f"expected every record exactly once, got {len(ids)}"
    assert len(set(ids)) == 25


def test_heavy_overlap_still_delivers_every_record(ogc_helper_module, tmp_path):
    """Rewinding 9 of every 10 advances by only one record per request, but it
    does advance, so the harvest must grind to completion rather than stop
    short. Before the fix this returned 30 items covering only 21 of 25 and
    reported success, and their 5-day cleanup would have deleted the other 4."""
    with StubOGC(total=25, page_size=10, mode="overlapping", overlap=9) as stub:
        ids = [f["id"] for f in islice(
            _harvester(ogc_helper_module, stub.base, tmp_path).iter_items("c"), 200)]
    assert sorted(set(ids)) == sorted(ids), "a record was delivered twice"
    assert len(ids) == 25


def test_overlap_as_wide_as_the_page_never_advances_and_is_caught(ogc_helper_module, tmp_path):
    """At overlap == page_size the rewind cancels the offset exactly, so no
    page ever carries a new id. That is the boundary where recovery becomes
    impossible and the no-new-id guard has to fire."""
    with StubOGC(total=25, page_size=10, mode="overlapping", overlap=10) as stub:
        with pytest.raises(RuntimeError, match="did not advance"):
            list(islice(_harvester(ogc_helper_module, stub.base, tmp_path).iter_items("c"), 200))


def test_next_links_that_stop_early_are_recovered_by_the_offset_fallback(
    ogc_helper_module, tmp_path
):
    """A server that pages by rel=next, reports numberMatched 25, then simply
    stops offering a next link after 20 records. The remaining 5 are still
    reachable by offset, so the right outcome is to fetch them, not to fail.
    This only works if the offset is tracked while following next links; when
    it was not, the fallback re-requested a URL already seen and raised."""
    with StubOGC(total=25, page_size=10, mode="short_next") as stub:
        ids = [f["id"] for f in islice(
            _harvester(ogc_helper_module, stub.base, tmp_path).iter_items("c"), 200)]
    assert len(ids) == 25
    assert len(set(ids)) == 25


def test_a_server_that_advertises_more_than_it_holds_is_reported(ogc_helper_module, tmp_path):
    """numberMatched says 30, the server holds 25. That is what a source
    republished mid-harvest looks like, and failing the night is the safe
    outcome: their cleanup tolerates a missed night, never a partial dump."""
    with StubOGC(total=25, page_size=10, mode="overcounts") as stub:
        with pytest.raises(RuntimeError, match="harvest incomplete"):
            list(islice(_harvester(ogc_helper_module, stub.base, tmp_path).iter_items("c"), 200))


def test_a_next_link_to_another_host_is_refused(ogc_helper_module, tmp_path):
    with StubOGC(total=25, mode="foreign_next") as stub:
        with pytest.raises(RuntimeError, match="different host"):
            list(_harvester(ogc_helper_module, stub.base, tmp_path).iter_items("c"))


def test_a_500_midway_aborts_rather_than_truncating(ogc_helper_module, tmp_path):
    """Their cleanup deletes documents not re-seen within 5 days, so a partial
    dump silently removes live records. It must raise, not return a short list."""
    with StubOGC(total=25, mode="fail_midway") as stub:
        with pytest.raises(Exception, match="Status 500"):
            list(_harvester(ogc_helper_module, stub.base, tmp_path).iter_items("c"))


def test_collections_must_be_named(ogc_helper_module, tmp_path):
    with pytest.raises(ValueError, match="collections"):
        ogc_helper_module.OGCAPIRecordsHarvester(
            url="https://example.org/ogc", collections=[], logfile=str(tmp_path / "h.log"))


def test_never_sends_q_or_a_property_filter(ogc_helper_module, tmp_path):
    """pygeoapi discards q and returns everything with HTTP 200; array and jsonb
    property filters return 500. Only paging parameters may ever be sent."""
    with StubOGC(total=25, mode="next") as stub:
        list(_harvester(ogc_helper_module, stub.base, tmp_path).iter_items("c"))
    assert stub.requests
    for path in stub.requests:
        sent = set(parse_qs(urlparse(path).query))
        assert sent <= {"f", "limit", "offset"}, f"unexpected parameters {sent} in {path}"


def test_never_requests_conformance_or_collection_discovery(ogc_helper_module, tmp_path):
    with StubOGC(total=25, mode="next") as stub:
        list(_harvester(ogc_helper_module, stub.base, tmp_path).iter_items("c"))
    for path in stub.requests:
        route = urlparse(path).path
        assert "conformance" not in route
        assert route != "/collections", "collection discovery must never happen"


def test_items_url_tolerates_a_trailing_slash(ogc_helper_module, tmp_path):
    h = _harvester(ogc_helper_module, "https://example.org/ogc/", tmp_path)
    assert h.items_url("arc-records") == "https://example.org/ogc/collections/arc-records/items"