"""Safety checks for documentation and executable public examples."""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
RAW_TOKEN_PATTERN = re.compile(r"owa_pat-[A-Za-z0-9_-]{20,}")
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
FORBIDDEN_PUBLIC_TEXT = (
    "/home/",
    "C:\\",
    "parampilot_backend",
    "parampilot_worker",
)


def _public_guide_files() -> list[Path]:
    """Collect all documentation and example files shipped in the source archive.

    Returns:
        Stable list of public Markdown and Python guide paths.

    """
    return [
        *sorted(PACKAGE_ROOT.glob("*.md")),
        *sorted((PACKAGE_ROOT / "docs").rglob("*.md")),
        *sorted((PACKAGE_ROOT / "examples").rglob("*.py")),
    ]


def test_public_guides_contain_no_raw_token_or_private_path() -> None:
    """Shipped guides must use placeholders and remain monorepo-independent."""
    files = _public_guide_files()
    assert files

    for path in files:
        text = path.read_text(encoding="utf-8")
        assert RAW_TOKEN_PATTERN.search(text) is None, path
        assert not [value for value in FORBIDDEN_PUBLIC_TEXT if value in text], path


def test_public_markdown_relative_links_resolve_inside_package() -> None:
    """Every shipped relative Markdown link must resolve within public source."""
    markdown = [path for path in _public_guide_files() if path.suffix == ".md"]
    assert markdown

    for path in markdown:
        text = path.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK_PATTERN.findall(text):
            target = raw_target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = (path.parent / target).resolve()
            assert resolved.is_relative_to(PACKAGE_ROOT), (path, raw_target)
            assert resolved.exists(), (path, raw_target)
