"""The paging loop, and the rules that make this reader safe to point at a
server we did not write. Reachable offline: their fetch only special-cases
file:// URLs, so an http stub exercises the real code path."""
from __future__ import annotations

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