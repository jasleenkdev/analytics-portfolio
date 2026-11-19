"""Assemble the GitHub Pages site: one landing page plus each project's dashboard."""
from __future__ import annotations

import html
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PROJECTS = [
    ("p1", "p1-fulfilment-ops"),
    ("p2", "p2-experimentation"),
    ("p3", "p3-customer-product"),
]


def _title(page: Path) -> str:
    match = re.search(r"<title>(.*?)</title>", page.read_text(encoding="utf-8"), re.S)
    return match.group(1).strip() if match else page.parent.parent.name


def build() -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    items = []
    for slug, folder in PROJECTS:
        page = ROOT / folder / "docs" / "index.html"
        if not page.exists():
            continue
        (SITE / slug).mkdir()
        shutil.copy(page, SITE / slug / "index.html")
        items.append(f'<li><a href="{slug}/">{html.escape(_title(page))}</a></li>')
    (SITE / "index.html").write_text(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Analytics portfolio</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:48px auto;padding:0 16px;"
        "color:#1f2328;background:#fff;line-height:1.5}a{color:#0b5cad}</style></head><body>"
        "<h1>Analytics portfolio</h1>"
        "<p>Three analytics projects on <strong>simulated</strong> online-retail and delivery data. "
        "Every number on these dashboards comes from a seeded synthetic generator, not from any real company.</p>"
        f"<ul>{''.join(items)}</ul></body></html>",
        encoding="utf-8",
    )
    print(f"site built with {len(items)} dashboard(s) at {SITE}")


if __name__ == "__main__":
    build()
