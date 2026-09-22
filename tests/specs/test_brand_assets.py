"""Unit tests for the brand asset generator."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from lxml import etree

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import generate_brand_assets as gen  # noqa: E402

SVG_NS = "http://www.w3.org/2000/svg"

_SOURCE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
    '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
    '"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n'
    '<svg width="100%" height="100%" viewBox="0 0 1600 750" version="1.1" '
    'xmlns="http://www.w3.org/2000/svg">'
    '<metadata>editor junk</metadata>'
    '<path d="M0 0 L10 10"/>'
    "</svg>"
)


def test_render_sets_intrinsic_size_from_viewbox():
    root = etree.fromstring(gen.render(_SOURCE, "DataPLANT").encode("utf-8"))
    assert root.get("width") == "1600"
    assert root.get("height") == "750"
    assert root.get("viewBox") == "0 0 1600 750"


def test_render_strips_doctype():
    out = gen.render(_SOURCE, "DataPLANT")
    assert "DOCTYPE" not in out
    assert "svg11.dtd" not in out


def test_render_strips_editor_metadata():
    out = gen.render(_SOURCE, "DataPLANT")
    assert "editor junk" not in out


def test_render_injects_accessible_title():
    root = etree.fromstring(gen.render(_SOURCE, "DataPLANT").encode("utf-8"))
    assert root.get("role") == "img"
    title = root.find(f"{{{SVG_NS}}}title")
    assert title is not None
    assert title.text == "DataPLANT"
    assert list(root).index(title) == 0, "title must be the first child"


def test_render_stamps_generated_header():
    assert gen.render(_SOURCE, "DataPLANT").startswith("<!-- GENERATED FILE")


def test_render_rejects_source_without_viewbox():
    bad = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'
    with pytest.raises(ValueError, match="viewBox"):
        gen.render(bad, "DataPLANT")


@pytest.mark.parametrize("name", ["dataplant-logo.svg", "dataplant-mark.svg"])
def test_generated_outputs_are_template_ready(name: str):
    path = REPO_ROOT / "ogc" / "static" / "img" / name
    assert path.exists(), f"{name} not generated; run make brand-assets"
    text = path.read_text(encoding="utf-8")
    assert "DOCTYPE" not in text

    root = etree.fromstring(text.encode("utf-8"))
    _, _, vb_width, vb_height = root.get("viewBox").replace(",", " ").split()
    assert float(root.get("width")) == float(vb_width)
    assert float(root.get("height")) == float(vb_height)
    assert root.get("role") == "img"
    assert root.find(f"{{{SVG_NS}}}title") is not None


def test_check_mode_reports_in_sync():
    # After generation (committed files present), --check must pass.
    assert gen.main(["--check"]) == 0


def test_header_logo_is_the_minimal_mark():
    """Spec R1: the header shows the minimal square mark, not the wordmark."""
    path = REPO_ROOT / "ogc" / "static" / "img" / "dataplant-logo.svg"
    root = etree.fromstring(path.read_text(encoding="utf-8").encode("utf-8"))
    assert root.get("viewBox") == "0 0 1622 1621"


def test_only_used_sources_are_vendored():
    """Spec D7: vendor only what a generated asset is built from."""
    src = REPO_ROOT / "ogc" / "brand" / "src"
    vendored = sorted(p.stem for p in src.glob("*.svg"))
    assert vendored == sorted(gen.ASSETS)