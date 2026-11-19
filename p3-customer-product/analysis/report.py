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
    dq = export_csv(con, {"data_quality_report": "SELECT * FROM dq_report"}, OUT)["data_quality_report"]
    render(TEMPLATES, "data_quality_report.md.j2", OUT / "data_quality_report.md",
           table=md_table(dq, {"failing_rows": INT, "total_rows": INT, "failing_pct": lambda v: f"{v:.3f}%"}))


EXPORTS = {
    "funnel_overall": "SELECT * FROM funnel_overall",
    "funnel_segment_month": "SELECT * FROM funnel_segment_month",
    "funnel_dropoffs": "SELECT * FROM funnel_dropoffs",
    "cohort_retention": "SELECT * FROM cohort_retention",
    "repeat_curve": "SELECT * FROM repeat_curve",
    "retention_drivers": "SELECT * FROM retention_drivers",
    "retention_model": "SELECT * FROM retention_model",
    "rfm_segments": "SELECT * FROM rfm_segments",
    "rfm_customers": "SELECT * FROM rfm ORDER BY customer_id",
    "abc_xyz": "SELECT * FROM abc_xyz",
    "abc_xyz_matrix": "SELECT * FROM abc_xyz_matrix",
    "basket_affinity": "SELECT * FROM basket_affinity",
    "wastage_node_sku": "SELECT * FROM wastage_node_sku ORDER BY waste_cost DESC, node_id, sku_id",
    "wastage_node_category": "SELECT * FROM wastage_node_category",
    "assortment_recommendations": "SELECT * FROM assortment_recommendations ORDER BY node_id, action, sku_id",
    "assortment_node_summary": "SELECT * FROM assortment_node_summary",
}


def run() -> None:
    cfg = load_config(PROJECT)
    findings = json.loads((OUT / "findings.json").read_text())
    con = open_db(read_only=True)
    try:
        data_quality(con)
        export_csv(con, EXPORTS, OUT / "kpi")
        workbook.build(con, cfg, OUT / "p3_assortment_wastage.xlsx")
        dashboard.build(con, findings, cfg, PROJECT / "docs" / "index.html")
        crosscheck.run(con, cfg)
        narrative.run(con, findings, cfg)
    finally:
        con.close()
