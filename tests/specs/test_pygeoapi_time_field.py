"""Every served collection must declare a time_field.

`datetime` is a core OGC API query parameter. pygeoapi's SQL provider raises
ProviderQueryError from _get_datetime_filter when time_field is undeclared
(provider/sql.py:534 in 0.23.4), which the API layer turns into an HTTP 500 -
not a 400. So an undeclared time_field is not a missing nicety, it is a
conformance failure that crashes on a perfectly legal request.

Runs offline against the committed generated file, because that is what the
container is handed.
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "pygeoapi-config.yml"
VIEWS = REPO_ROOT / "sql" / "catalog_views.sql"


def _providers() -> list[tuple[str, dict]]:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    out = []
    for name, resource in config["resources"].items():
        if resource.get("type") != "collection":
            continue
        for provider in resource["providers"]:
            out.append((name, provider))
    return out


def test_every_collection_declares_a_time_field():
    missing = [name for name, p in _providers() if not p.get("time_field")]
    assert not missing, (
        f"collections without time_field will return HTTP 500 for any "
        f"?datetime= request: {missing}"
    )


def test_the_declared_time_field_is_selected_by_the_backing_view():
    # A time_field naming a column the view does not select fails at query
    # time with an AttributeError on the reflected model, which is the same
    # 500 by another route.
    views_sql = VIEWS.read_text(encoding="utf-8")
    for name, provider in _providers():
        field = provider.get("time_field")
        if not field:
            continue
        assert f"AS {field}" in views_sql, (
            f"{name} declares time_field '{field}' but no view in "
            f"sql/catalog_views.sql selects a column of that name"
        )


def test_the_time_field_is_also_exposed_as_a_property():
    # pygeoapi filters output columns through the provider's `properties`
    # list; a time_field absent from it is filterable but invisible, which
    # makes a datetime-filtered response impossible to interpret.
    for name, provider in _providers():
        field = provider.get("time_field")
        if not field:
            continue
        assert field in provider.get("properties", []), (
            f"{name} filters on '{field}' but does not return it"
        )
