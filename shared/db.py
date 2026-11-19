"""DuckDB and config helpers shared by the three projects."""
from __future__ import annotations

import tomllib
from pathlib import Path

import duckdb


def load_config(project_dir: Path) -> dict:
    with open(Path(project_dir) / "config.toml", "rb") as f:
        return tomllib.load(f)


def connect(db_path: Path, sql_vars: dict | None = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open the project database and expose config values to SQL as getvariable('name')."""
    con = duckdb.connect(str(db_path), read_only=read_only)
    for name, value in (sql_vars or {}).items():
        con.execute(f"SET VARIABLE {name} = ?", [value])
    return con


def run_sql_file(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    try:
        con.execute(Path(path).read_text())
    except duckdb.Error as exc:
        raise RuntimeError(f"SQL failed in {path}: {exc}") from exc


def run_sql_dir(con: duckdb.DuckDBPyConnection, sql_dir: Path, prefix: str = "") -> list[str]:
    """Run every sql/<prefix>*.sql file in name order; numbering in file names encodes dependencies."""
    files = sorted(Path(sql_dir).glob(f"{prefix}*.sql"))
    for f in files:
        run_sql_file(con, f)
    return [f.name for f in files]


def query_df(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None):
    return con.execute(sql, params or []).df()
