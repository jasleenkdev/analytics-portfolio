"""Report stage: CSV exports, workbook, dashboard and generated markdown."""
from __future__ import annotations

from pathlib import Path

from analysis.run_sql import open_db
from shared.reporting import export_csv, md_table, render

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "outputs"
TEMPLATES = PROJECT / "templates"
INT = lambda v: f"{int(v):,d}"  # noqa: E731


def data_quality(con) -> None:
    dq = export_csv(con, {"data_quality_report": "SELECT * FROM dq_report"}, OUT)["data_quality_report"]
    render(TEMPLATES, "data_quality_report.md.j2", OUT / "data_quality_report.md",
           table=md_table(dq, {"failing_rows": INT, "total_rows": INT, "failing_pct": lambda v: f"{v:.3f}%"}))


def run() -> None:
    con = open_db(read_only=True)
    try:
        data_quality(con)
    finally:
        con.close()
