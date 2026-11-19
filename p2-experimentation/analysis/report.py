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
    frames = export_csv(con, {"data_quality_report": "SELECT * FROM dq_report",
                              "assignment_daily": "SELECT * FROM dq_assignment_daily"}, OUT)
    table = md_table(frames["data_quality_report"], {"failing_rows": INT, "total_rows": INT,
                                                     "failing_pct": lambda v: f"{v:.3f}%"})
    daily = frames["assignment_daily"].assign(assign_date=lambda d: d.assign_date.astype(str))
    render(TEMPLATES, "data_quality_report.md.j2", OUT / "data_quality_report.md",
           table=table, daily=md_table(daily, {"n_control": INT, "n_treatment": INT}))


def run() -> None:
    con = open_db(read_only=True)
    try:
        data_quality(con)
    finally:
        con.close()
