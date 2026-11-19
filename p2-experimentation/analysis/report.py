"""Report stage: CSV exports, workbook, dashboard and generated markdown."""
from __future__ import annotations

from pathlib import Path

import json

from analysis import crosscheck, dashboard, narrative, workbook
from analysis.run_sql import open_db
from shared.db import load_config
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


EXPORTS = {
    "exp_arm_summary": "SELECT * FROM exp_arm_summary",
    "exp_ratio_moments": "SELECT * FROM exp_ratio_moments",
    "exp_week_summary": "SELECT * FROM exp_week_summary",
    "exp_segment_summary": "SELECT * FROM exp_segment_summary",
    "exp_results": "SELECT * FROM exp_results",
    "exp_novelty": "SELECT * FROM exp_novelty",
    "exp_segments": "SELECT * FROM exp_segments",
    "exp_interactions": "SELECT * FROM exp_interactions",
    "exp_basket_hist": "SELECT * FROM exp_basket_hist",
    "pilot_weekly": "SELECT * FROM pilot_weekly",
    "pilot_2x2": "SELECT * FROM pilot_2x2",
    "pilot_did": "SELECT * FROM pilot_did",
    "pilot_event_study": "SELECT * FROM pilot_event_study ORDER BY metric, rel_week",
}


def run() -> None:
    cfg = load_config(PROJECT)
    findings = json.loads((OUT / "findings.json").read_text())
    con = open_db(read_only=True)
    try:
        data_quality(con)
        export_csv(con, EXPORTS, OUT / "kpi")
        workbook.build(con, cfg, findings, OUT / "p2_experiment_readout.xlsx")
        dashboard.build(con, findings, cfg, PROJECT / "docs" / "index.html")
        crosscheck.run(con, cfg)
        narrative.run(findings, cfg)
    finally:
        con.close()
