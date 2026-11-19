"""Execute the project's SQL files against the generated database."""
from __future__ import annotations

from pathlib import Path

from shared.db import connect, load_config, run_sql_dir

PROJECT = Path(__file__).resolve().parents[1]
DB = PROJECT / "data" / "experiments.duckdb"


def sql_vars(cfg: dict) -> dict:
    s, a = cfg["sim"], cfg["analysis"]
    return {
        "experiment_start": s["experiment_start"], "assignment_days": s["assignment_days"],
        "observation_days": s["observation_days"], "pre_period_days": s["pre_period_days"],
        "pilot_start": s["pilot_start"], "pilot_pre_days": s["pilot_pre_days"], "pilot_post_days": s["pilot_post_days"],
        "rider_cost_per_hour": a["rider_cost_per_hour"], "sla_minutes": a["sla_minutes"],
        "control_free_threshold": cfg["promo"]["control_free_threshold"],
        "treatment_free_threshold": cfg["promo"]["treatment_free_threshold"],
    }


def open_db(read_only: bool = False):
    return connect(DB, sql_vars(load_config(PROJECT)), read_only=read_only)


def run(prefix: str = "") -> list[str]:
    con = open_db()
    try:
        return run_sql_dir(con, PROJECT / "sql", prefix)
    finally:
        con.close()
