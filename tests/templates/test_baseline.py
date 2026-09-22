"""Every overridden template renders in the pygeoapi-equivalent environment."""
from __future__ import annotations

from pathlib import Path

import pytest

from .builders import (
    COLLECTION_TPL,
    ITEM_TPL,
    ITEMS_TPL,
    MULTIPOINT,
    POINT,
    collection_data,
    feature,
    item_data,
    items_data,
)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "ogc" / "templates"


@pytest.mark.parametrize("geometry", [None, POINT, MULTIPOINT], ids=["null", "point", "multipoint"])
def test_item_page_renders(render, geometry):
    html = render(ITEM_TPL, item_data(geometry=geometry))
    assert "dataplant.css" in html
    assert "Worked example record" in html


def test_items_page_renders(render):
    html = render(ITEMS_TPL, items_data([feature("dataplant-a"), feature("dataplant-b")]))
    assert "dp-result" in html


def test_collection_page_renders(render):
    html = render(COLLECTION_TPL, collection_data())
    assert "INTERPLANT ARC records" in html


@pytest.mark.xfail(reason="spec R5: fixed in the next plan task", strict=True)
def test_no_relative_links_in_any_template():
    """pygeoapi serves .../items without a trailing slash, so a relative
    href resolves one path segment too high (spec R5)."""
    offenders = [
        f"{path.relative_to(TEMPLATE_DIR)}: {line.strip()}"
        for path in sorted(TEMPLATE_DIR.rglob("*.html"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if 'href="./' in line or 'href="../' in line
    ]
    assert not offenders, "relative links:\n" + "\n".join(offenders)