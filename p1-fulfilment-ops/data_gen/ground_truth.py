"""Render GROUND_TRUTH.md from the generator's plant file (used by the generator only)."""
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
    start = pd.Timestamp(cfg["sim"]["start_date"])
    day = lambda d: (start + pd.Timedelta(days=d)).date().isoformat()  # noqa: E731
    resolved = json.loads((project_dir / "data" / "planted_entities.json").read_text())
    sc = plants["stockout_cluster"]
    st = plants["storm"]
    env = Environment(loader=FileSystemLoader(project_dir / "templates"), undefined=StrictUndefined,
                      keep_trailing_newline=True)
    text = env.get_template("GROUND_TRUTH.md.j2").render(
        start=day(0), end=day(cfg["sim"]["days"] - 1), days=cfg["sim"]["days"], sla=cfg["ops"]["sla_minutes"],
        us=plants["understaffing"], storm=st, storm_nodes=resolved["storm_nodes"],
        storm_dates=[day(d) for d in range(st["start_day"], st["start_day"] + st["days"])],
        sc=sc, cluster_skus=resolved["stockout_cluster_skus"], dq=plants["data_quality"], pc=plants["process_change"],
        pc_date=day(plants["process_change"]["change_day"]),
        picker_util=cfg["ops"]["picker_target_utilisation"], rider_util=cfg["ops"]["rider_target_utilisation"],
    )
    out = project_dir / "GROUND_TRUTH.md"
    out.write_text(text)
    return out
