"""Every link is absolute and lands on a real page (spec R5)."""
from __future__ import annotations

import re

from .builders import (
    BASE,
    COLLECTION_TPL,
    COLLECTION_URL,
    ITEM_TPL,
    ITEMS,
    ITEMS_TPL,
    collection_data,
    feature,
    item_data,
    items_data,
)


def _crumbs(html: str) -> str:
    return html.split('class="crumbs"', 1)[1].split("<span", 1)[0]


def test_items_list_links_each_record_to_its_item_page(render):
    html = render(ITEMS_TPL, items_data([feature("dataplant-a"), feature("dataplant-b")]))
    hrefs = re.findall(r'class="dp-result__title">\s*<a href="([^"]+)"', html)
    assert hrefs == [f"{ITEMS}/dataplant-a", f"{ITEMS}/dataplant-b"]


def test_items_list_breadcrumbs(render):
    crumbs = _crumbs(render(ITEMS_TPL, items_data([feature("dataplant-a")])))
    for href in (f"{BASE}/collections", COLLECTION_URL, ITEMS):
        assert f'href="{href}"' in crumbs, href
    assert "INTERPLANT ARC records" in crumbs


def test_items_list_is_titled_with_the_collection(render):
    html = render(ITEMS_TPL, items_data([feature("dataplant-a")]))
    assert re.search(r"<h1>\s*INTERPLANT ARC records\s*</h1>", html)


def test_collection_page_crumb_is_absolute(render):
    assert f'href="{COLLECTION_URL}"' in _crumbs(render(COLLECTION_TPL, collection_data()))


def test_item_page_crumbs_and_navigation(render):
    html = render(ITEM_TPL, item_data(record_id="dataplant-x"))
    crumbs = _crumbs(html)
    assert f'href="{ITEMS}"' in crumbs
    assert f'href="{ITEMS}/dataplant-x"' in crumbs
    assert f'href="{ITEMS}/dataplant-prev"' in html
    assert f'href="{ITEMS}/dataplant-next"' in html


def test_item_page_without_neighbours_has_no_nav(render):
    html = render(ITEM_TPL, item_data(prev=None, next_=None))
    assert "&laquo;" not in html and "&raquo;" not in html