"""Pin pygeoapi 0.23.4's limitations so an upgrade tells us they are gone.

Each test asserts the BEHAVIOUR WE WANT and is marked xfail, so today it
reports XFAIL and after a pygeoapi upgrade that fixes it, XPASS - which is the
signal to drop the xfail and update the "Known OGC API limitations" section of
deploy/README.md.

Do not "fix" these by weakening the assertion to match today's behaviour. The
assertion is the specification; the xfail is the dated concession.
"""
from __future__ import annotations

import pytest
import requests

COLLECTION = "arc-records"


@pytest.mark.xfail(
    reason="pygeoapi 0.23.4 PostgreSQLProvider.query accepts q= and never uses "
    "it (no _get_q_filter in provider/sql.py), so every q returns the full "
    "collection with HTTP 200",
    strict=True,
)
def test_free_text_search_excludes_non_matching_records(
    pygeoapi_url: str, pygeoapi_reachable: bool
):
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    base = f"{pygeoapi_url}/collections/{COLLECTION}/items"
    total = requests.get(base, params={"limit": 1, "f": "json"}, timeout=30).json()[
        "numberMatched"
    ]
    nonsense = requests.get(
        base, params={"q": "zzzznonexistentzzz", "limit": 1, "f": "json"}, timeout=30
    ).json()["numberMatched"]
    assert nonsense < total, (
        "q= matched every record, so it was discarded rather than applied; a "
        "client cannot distinguish this from a genuine full match"
    )


@pytest.mark.xfail(
    reason="pygeoapi 0.23.4 _get_property_filters emits scalar == against a "
    "text[] column, so PostgreSQL raises malformed array literal",
    strict=True,
)
@pytest.mark.parametrize("field,value", [
    ("omics_domains", "imaging"),
    ("organism", "Arabidopsis thaliana"),
    ("keywords", "drought"),
])
def test_filtering_on_an_array_property_does_not_return_500(
    pygeoapi_url: str, pygeoapi_reachable: bool, field: str, value: str
):
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    r = requests.get(
        f"{pygeoapi_url}/collections/{COLLECTION}/items",
        params={field: value, "limit": 1, "f": "json"},
        timeout=30,
    )
    assert r.status_code != 500, (
        f"filtering on the array column {field} crashed the provider"
    )


@pytest.mark.xfail(
    reason="pygeoapi 0.23.4 emits its conformance list from its own "
    "capabilities, not from our config, so a read-only deployment still "
    "advertises the transactions class",
    strict=True,
)
def test_conformance_does_not_advertise_transactions_on_a_read_only_service(
    pygeoapi_url: str, pygeoapi_reachable: bool
):
    if not pygeoapi_reachable:
        pytest.skip("pygeoapi not reachable")
    classes = requests.get(
        f"{pygeoapi_url}/conformance", params={"f": "json"}, timeout=30
    ).json()["conformsTo"]
    txn = "http://www.opengis.net/spec/ogcapi-features-4/1.0/conf/create-replace-delete"
    assert txn not in classes, (
        "the service advertises create-replace-delete but refuses every write "
        "with 'Collection is not editable'"
    )
