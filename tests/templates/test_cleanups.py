"""Standards-review clean-ups (spec section 12)."""
from __future__ import annotations

import re
from pathlib import Path

from .builders import (
    COLLECTION_TPL,
    ITEM_TPL,
    ITEMS_TPL,
    collection_data,
    feature,
    item_data,
    items_data,
)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "ogc" / "templates"


def _meta(html: str, attr: str, name: str) -> str:
    match = re.search(rf'<meta {attr}="{re.escape(name)}"\s+content="([^"]*)"', html)
    assert match, f"no meta {attr}={name}"
    return match.group(1)


def test_record_abstract_is_the_meta_description(render):
    html = render(ITEM_TPL, item_data(description="Short abstract."))
    assert _meta(html, "name", "description") == "Short abstract."
    assert _meta(html, "property", "og:description") == "Short abstract."


def test_other_pages_fall_back_to_the_catalogue_description(render, config):
    html = render(COLLECTION_TPL, collection_data())
    assert _meta(html, "name", "description") == config["metadata"]["identification"]["description"]


def test_abstract_toggle_labels_are_translatable(render):
    html = render(ITEM_TPL, item_data())
    assert 'data-more="Show more"' in html
    assert 'data-less="Show less"' in html
    assert "'Show less'" not in html, "JS must read the label from data-less"


def test_tag_markup_lives_in_one_macro():
    for name in (
        "collections/items/item.html",
        "collections/items/index.html",
        "collections/collection.html",
    ):
        text = (TEMPLATE_DIR / name).read_text(encoding="utf-8")
        assert 'import dp_tags' in text, name
        assert "{% macro" not in text, name


def test_tags_still_render_everywhere(render):
    assert 'dp-tag--omics">genomics' in render(ITEM_TPL, item_data())
    assert 'dp-tag--omics">genomics' in render(ITEMS_TPL, items_data([feature("dataplant-a")]))
    assert 'dp-tag--keyword">arc' in render(COLLECTION_TPL, collection_data())


def test_no_dead_blocks_in_item_template():
    text = (TEMPLATE_DIR / "collections/items/item.html").read_text(encoding="utf-8")
    assert "{% block tags %}" not in text
    assert "{% block map %}" not in text