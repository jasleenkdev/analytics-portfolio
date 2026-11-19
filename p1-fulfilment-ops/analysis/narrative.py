"""Render README.md and memo.md from findings.json."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

from shared.reporting import render, render_shared

PROJECT = Path(__file__).resolve().parents[1]


def links() -> dict:
    with open(PROJECT.parent / "portfolio.toml", "rb") as f:
        return tomllib.load(f)["links"]


def run(con, findings: dict, cfg: dict) -> None:
    dq_excluded = con.execute("SELECT count(*) FROM dq_excluded_orders").fetchone()[0]
    dq_issues = sum(1 for r in findings["data_quality"] if r["status"] == "issue")
    cc = json.loads((PROJECT / "outputs" / "crosscheck.json").read_text())
    ctx = dict(f=findings, cfg=cfg, links=links(), dq_excluded=dq_excluded, dq_issues=dq_issues, cc=cc,
               storm_row=next((r for r in cc["rows"] if r["planted"].startswith("B.")), None),
               found_vs_planted=render_shared("crosscheck_section.md.j2", cc=cc))
    render(PROJECT / "templates", "memo.md.j2", PROJECT / "memo.md", **ctx)
    render(PROJECT / "templates", "README.md.j2", PROJECT / "README.md", **ctx)
