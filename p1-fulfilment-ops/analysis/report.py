"""Report stage: CSV exports and generated markdown."""
from __future__ import annotations

from pathlib import Path

from analysis.run_sql import open_db
from shared.reporting import export_csv, md_table, render

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "outputs"
TEMPLATES = PROJECT / "templates"


def data_quality(con) -> None:
    dq = export_csv(con, {"data_quality_report": "SELECT * FROM dq_report"}, OUT)["data_quality_report"]
    excluded, share = con.execute("""
        SELECT count(*) FILTER (WHERE NOT timing_valid), avg(CAST(NOT timing_valid AS DOUBLE))
        FROM order_timeline WHERE status = 'delivered'""").fetchone()
    repaired = con.execute("""
        SELECT count(*) FROM order_events r JOIN events_clean c USING (event_id)
        WHERE r.rider_id IS NULL AND c.rider_id IS NOT NULL""").fetchone()[0]
    table = md_table(dq[["check_name", "table_name", "failing_rows", "total_rows", "failing_pct", "status", "action"]],
                     {"failing_rows": lambda v: f"{int(v):,d}", "total_rows": lambda v: f"{int(v):,d}",
                      "failing_pct": lambda v: f"{v:.3f}%"})
    render(TEMPLATES, "data_quality_report.md.j2", OUT / "data_quality_report.md",
           table=table, excluded=excluded, excluded_share=share, repaired=repaired)


def run() -> None:
    con = open_db(read_only=True)
    try:
        data_quality(con)
    finally:
        con.close()
