"""Render README.md and memo.md from findings.json."""
from __future__ import annotations

import tomllib
from pathlib import Path

from shared.reporting import render

PROJECT = Path(__file__).resolve().parents[1]


def context(findings: dict, cfg: dict) -> dict:
    p, q = findings["promo"], findings["pilot"]
    r = {f"{x['metric']}|{x['method']}": x for x in p["results"] if x["population"] == "analysis"}
    full = next(x for x in p["results"] if x["population"] != "analysis")
    nov = {(x["week"], x["metric"]): x for x in p["novelty"]}
    weeks = sorted({w for w, _ in nov})
    sig_dims = [x for x in p["interactions"] if x["significant_adjusted"]]
    seg = {(x["metric"], x["dimension"], x["segment"]): x for x in p["segments"]}
    did = {x["metric"]: x for x in q["did"]}
    with open(PROJECT.parent / "portfolio.toml", "rb") as f:
        links = tomllib.load(f)["links"]
    return dict(f=findings, p=p, q=q, r=r, full=full, nov=nov, w1=weeks[0], wl=weeks[-1], sig_dims=sig_dims,
                seg=seg, did=did, cfg=cfg, links=links,
                dq_issues=[x for x in findings["data_quality"] if x["status"] == "issue"])


def run(findings: dict, cfg: dict) -> None:
    ctx = context(findings, cfg)
    render(PROJECT / "templates", "memo.md.j2", PROJECT / "memo.md", **ctx)
    render(PROJECT / "templates", "README.md.j2", PROJECT / "README.md", **ctx)
