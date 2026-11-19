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
    fd = plants["funnel_dropoff"]
    env = Environment(loader=FileSystemLoader(project_dir / "templates"), undefined=StrictUndefined, keep_trailing_newline=True)
    text = env.get_template("GROUND_TRUTH.md.j2").render(
        sim=cfg["sim"], fd=fd, rt=plants["retention"], af=plants["affinity"], wa=plants["wastage"],
        hg=plants["hidden_gems"], ent=ent,
        release_date=(pd.Timestamp(cfg["sim"]["start_date"]) + pd.Timedelta(days=fd["release_day"])).date())
    out = project_dir / "GROUND_TRUTH.md"
    out.write_text(text)
    return out
