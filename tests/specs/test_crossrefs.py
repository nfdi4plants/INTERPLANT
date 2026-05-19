"""Every relative link in spec markdown files must resolve to a real file."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SPECS_ROOT = Path(__file__).parent.parent.parent / "docs" / "specs"
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _markdown_files() -> list[Path]:
    return [p for p in SPECS_ROOT.rglob("*.md") if p.is_file()]


@pytest.mark.parametrize("md", _markdown_files(), ids=lambda p: p.name)
def test_markdown_links_resolve(md):
    content = md.read_text()
    broken: list[str] = []
    for match in LINK_RE.finditer(content):
        href = match.group(1)
        if href.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = (md.parent / href.split("#", 1)[0]).resolve()
        if not target.exists():
            broken.append(f"{md.name}: {href} -> {target}")
    assert broken == [], "Broken relative links:\n  " + "\n  ".join(broken)
