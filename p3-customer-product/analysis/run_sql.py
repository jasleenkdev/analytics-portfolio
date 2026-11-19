"""Execute the project's SQL files against the generated database."""
from __future__ import annotations

from pathlib import Path

from shared.db import connect, load_config, run_sql_dir

PROJECT = Path(__file__).resolve().parents[1]
DB = PROJECT / "data" / "customer_product.duckdb"


def sql_vars(cfg: dict) -> dict:
    return {"start_date": cfg["sim"]["start_date"], "days": cfg["sim"]["days"], **cfg["analysis"]}


def open_db(read_only: bool = False):
    return connect(DB, sql_vars(load_config(PROJECT)), read_only=read_only)


def run(prefix: str = "") -> list[str]:
    con = open_db()
    try:
        return run_sql_dir(con, PROJECT / "sql", prefix)
    finally:
        con.close()
