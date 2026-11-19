"""Render README.md and memo.md from findings.json."""
from __future__ import annotations

import tomllib
from pathlib import Path

import pandas as pd

from shared.reporting import md_table, render

PROJECT = Path(__file__).resolve().parents[1]


def run(con, findings: dict, cfg: dict) -> None:
    f = findings
    model = {m["term"]: m for m in f["retention"]["model"]}
    channels = sorted([m for t, m in model.items() if t.startswith("channel:")], key=lambda m: m["marginal_effect_pp"])
    drivers = {(d["driver"], d["level"]): d for d in f["retention"]["drivers"]}
    rfm = {r["segment"]: r for r in f["rfm"]}
    summary = {r["action"]: r for r in f["assortment"]["summary"]}
    abc = pd.DataFrame(f["abc_xyz"])
    a_class = abc[abc.abc == "A"]
    gems = [g for g in f["assortment"]["add_skus"] if g["ranged_nodes"] <= 2]
    names = dict(con.execute("SELECT sku_id, sku_name FROM skus").fetchall())
    appendix = con.execute("""
        SELECT node_id,
               count(*) FILTER (WHERE action = 'add') AS add_skus,
               round(sum(impact_low) FILTER (WHERE action = 'add')) AS add_low,
               round(sum(impact_high) FILTER (WHERE action = 'add')) AS add_high,
               count(*) FILTER (WHERE action = 'reduce depth') AS reduce_skus,
               round(sum(impact_low) FILTER (WHERE action = 'reduce depth')) AS waste_saved_low,
               round(sum(impact_high) FILTER (WHERE action = 'reduce depth')) AS waste_saved_high,
               count(*) FILTER (WHERE action = 'drop') AS drop_skus,
               round(sum(impact_low) FILTER (WHERE action = 'drop')) AS drop_net_low,
               round(sum(impact_high) FILTER (WHERE action = 'drop')) AS drop_net_high
        FROM assortment_recommendations GROUP BY node_id ORDER BY node_id""").df().fillna(0)
    fmt = {c: (lambda v: f"{v:,.0f}") for c in appendix.columns if c != "node_id"}
    with open(PROJECT.parent / "portfolio.toml", "rb") as fh:
        links = tomllib.load(fh)["links"]
    ctx = dict(f=f, cfg=cfg, model=model, channels=channels, drivers=drivers, rfm=rfm, summary=summary,
               a_skus=len(a_class) and int(a_class.skus.sum()), a_share=float(a_class.revenue_share.sum()),
               gems=gems, names=names, appendix=md_table(appendix, fmt), links=links,
               dq_issues=[d for d in f["data_quality"] if d["status"] == "issue"])
    render(PROJECT / "templates", "memo.md.j2", PROJECT / "memo.md", **ctx)
    render(PROJECT / "templates", "README.md.j2", PROJECT / "README.md", **ctx)
