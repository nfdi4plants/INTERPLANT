"""The served pygeoapi config must declare limits the way 0.19+ expects.

Runs offline against the committed file: the failure it guards is a silent
one in JSON and a hard 500 in HTML, so it must not depend on the dev stack
being up.
"""
from __future__ import annotations

from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parents[2] / "pygeoapi-config.yml"


def _server() -> dict:
    # The file carries ${VAR:-default} placeholders that pygeoapi expands at
    # load time; plain yaml reads them as strings, which is all this needs.
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["server"]


def test_the_limits_block_is_present_and_not_the_superseded_scalar():
    server = _server()
    assert "limit" not in server, (
        "pygeoapi 0.19+ ignores the scalar server.limit. Leaving it set capped "
        "every collection at the built-in default of 10, ignored the client's "
        "limit parameter, and made /items?f=html return HTTP 500 with "
        "UndefinedError: 'dict object' has no attribute 'limits'"
    )
    limits = server.get("limits")
    assert isinstance(limits, dict), "server.limits must be a mapping"


def test_the_items_template_keys_the_html_page_reads_are_defined():
    # templates/collections/items/index.html dereferences default_items
    # directly; an absent key is an UndefinedError, not a fallback.
    limits = _server()["limits"]
    for key in ("default_items", "max_items"):
        assert isinstance(limits.get(key), int), f"server.limits.{key} must be an int"
    assert limits["default_items"] <= limits["max_items"]
