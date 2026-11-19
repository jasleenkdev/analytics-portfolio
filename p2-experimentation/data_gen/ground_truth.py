"""Render GROUND_TRUTH.md from the plant file and resolved planted entities (generator only)."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, StrictUndefined

PROJECT = Path(__file__).resolve().parents[1]


def render(project_dir: Path = PROJECT) -> Path:
    with open(project_dir / "config.toml", "rb") as f:
        cfg = tomllib.load(f)
    with open(project_dir / "data_gen" / "plants.toml", "rb") as f:
        plants = tomllib.load(f)
    ent = json.loads((project_dir / "data" / "planted_entities.json").read_text())
    sim = cfg["sim"]
    start = pd.Timestamp(sim["experiment_start"])
    env = Environment(loader=FileSystemLoader(project_dir / "templates"), undefined=StrictUndefined, keep_trailing_newline=True)
    text = env.get_template("GROUND_TRUTH.md.j2").render(
        sim=sim, promo=cfg["promo"], srm=plants["srm"], pe=plants["promo_effect"], pl=plants["pilot_effect"],
        dq=plants["pilot_data_quality"], ent=ent, start=start.date(),
        assign_end=(start + pd.Timedelta(days=sim["assignment_days"] - 1)).date(),
        srm_date=(start + pd.Timedelta(days=plants["srm"]["day"])).date(),
        pilot_date=(pd.Timestamp(sim["pilot_start"]) + pd.Timedelta(days=sim["pilot_pre_days"])).date(),
    )
    out = project_dir / "GROUND_TRUTH.md"
    out.write_text(text)
    return out
