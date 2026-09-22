"""Render upstream DataPLANT brand SVGs into template-ready assets.

Single source of truth: ogc/brand/src/*.svg, byte-identical upstream copies.
Run `make brand-assets` (or `python scripts/generate_brand_assets.py`) to
refresh the committed generated files. `--check` re-renders in memory and
exits non-zero if the committed files differ.

The upstream files declare width="100%" height="100%", which gives them no
intrinsic size to lay out against inside the flex header, and they carry an
external DTD reference that strict XML parsers try to fetch. This script
fixes both, drops editor metadata so future logo diffs stay legible, and
injects a title element so screen readers announce the logo.
"""
from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "ogc" / "brand" / "src"
OUT_DIR = REPO_ROOT / "ogc" / "static" / "img"

SVG_NS = "http://www.w3.org/2000/svg"

_GENERATED_NOTE = (
    "GENERATED FILE - do not edit. Edit ogc/brand/src/*.svg and run "
    "`make brand-assets`."
)

# source stem -> (output filename, accessible title)
ASSETS = {
    "DataPLANT_logo_bg_transparent": ("dataplant-logo.svg", "DataPLANT"),
    "DataPLANT_logo_square_bg_transparent": ("dataplant-mark.svg", "DataPLANT mark"),
}


def _num(value: float) -> str:
    """Format a viewBox dimension without a trailing .0."""
    return str(int(value)) if value == int(value) else f"{value:g}"


def render(src_text: str, title: str) -> str:
    """Return a template-ready SVG string for one upstream source."""
    parser = etree.XMLParser(
        remove_blank_text=True,
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
    )
    root = etree.fromstring(src_text.encode("utf-8"), parser)

    view_box = root.get("viewBox")
    if not view_box:
        raise ValueError("source SVG has no viewBox, cannot derive intrinsic size")
    parts = view_box.replace(",", " ").split()
    if len(parts) != 4:
        raise ValueError(f"malformed viewBox: {view_box!r}")
    width, height = float(parts[2]), float(parts[3])

    root.set("width", _num(width))
    root.set("height", _num(height))
    root.set("role", "img")

    etree.strip_elements(root, f"{{{SVG_NS}}}metadata", with_tail=False)
    for existing in root.findall(f"{{{SVG_NS}}}title"):
        root.remove(existing)
    title_el = etree.Element(f"{{{SVG_NS}}}title")
    title_el.text = title
    root.insert(0, title_el)

    body = etree.tostring(root, pretty_print=True, encoding="unicode")
    return f"<!-- {_GENERATED_NOTE} -->\n{body}"


def render_all() -> dict[Path, str]:
    """Render every configured asset. Raises if a source is missing."""
    out: dict[Path, str] = {}
    for stem, (out_name, title) in sorted(ASSETS.items()):
        src = SRC_DIR / f"{stem}.svg"
        if not src.exists():
            raise FileNotFoundError(f"missing brand source: {src}")
        out[OUT_DIR / out_name] = render(src.read_text(encoding="utf-8"), title)
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    check = "--check" in argv
    try:
        rendered = render_all()
    except FileNotFoundError as exc:
        print(str(exc))
        return 1

    if check:
        stale = sorted(
            str(path.relative_to(REPO_ROOT))
            for path, text in rendered.items()
            if not path.exists() or path.read_text(encoding="utf-8") != text
        )
        if stale:
            print("out of sync (run make brand-assets): " + ", ".join(stale))
            return 1
        print("brand assets in sync")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, text in rendered.items():
        path.write_text(text, encoding="utf-8")
    print(f"wrote {len(rendered)} brand assets to {OUT_DIR.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())