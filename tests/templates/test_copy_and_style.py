"""Copy and styling decisions from spec section 12 (R2, R3, R4)."""
from __future__ import annotations

import re
from pathlib import Path

from .builders import ITEM_TPL, item_data

CSS = Path(__file__).resolve().parent.parent.parent / "ogc" / "static" / "css" / "dataplant.css"


def _footer(html: str) -> str:
    return html.split("<footer", 1)[1].split("</footer>", 1)[0]


def _css_rule(selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS.read_text())
    assert match, f"no CSS rule for {selector}"
    return match.group(1)


def test_footer_does_not_expose_contact_email(render, config):
    footer = _footer(render(ITEM_TPL, item_data()))
    assert config["metadata"]["contact"]["email"] not in footer
    assert "mailto:" not in footer


def test_footer_still_names_the_operator(render, config):
    assert config["metadata"]["provider"]["name"] in _footer(render(ITEM_TPL, item_data()))


def test_cta_reads_go_to_arc(render):
    html = render(ITEM_TPL, item_data())
    assert re.search(r'class="dp-cta"[^>]*>\s*Go to ARC\s*<', html)
    assert "Open the ARC" not in html


def test_card_labels_are_heavy_enough_to_read_as_heading_colour():
    rule = _css_rule(".dp-card__heading")
    assert "color: var(--dp-darkblue)" in rule
    assert "font-weight: 600" in rule


def test_record_card_terms_use_the_heading_colour():
    assert "color: var(--color-heading)" in _css_rule(".dp-card dt")


def test_header_logo_is_large_enough_to_read():
    """The upstream mark carries padding, so a 40px box rendered it at 16x32."""
    assert "height: 50px" in _css_rule(".dp-header__logo")