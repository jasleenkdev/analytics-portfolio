"""Report stage: CSV exports and generated markdown."""
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


KPI_EXPORTS = {
    "kpi_delivery_node": "SELECT * FROM kpi_delivery_node",
    "kpi_delivery_node_day": "SELECT * FROM kpi_delivery_node_day ORDER BY node_id, order_date",
    "kpi_network_daily": "SELECT * FROM kpi_network_daily",
    "kpi_node_hour_profile": "SELECT * FROM kpi_node_hour_profile",
    "kpi_defects_node": "SELECT * FROM kpi_defects_node",
    "kpi_defects_network": "SELECT coalesce(defect_type, 'ANY') AS defect_type, * EXCLUDE (defect_type) FROM kpi_defects_network",
    "kpi_fill_node_category": "SELECT * FROM kpi_fill_node_category",
    "kpi_inventory_node": "SELECT * FROM kpi_inventory_node",
    "kpi_riders_node": "SELECT * FROM kpi_riders_node",
    "kpi_delay_decomposition_node": "SELECT * FROM kpi_delay_decomposition_node",
    "anomaly_chronic": "SELECT * FROM anomaly_chronic",
    "anomaly_incidents": "SELECT * FROM anomaly_incidents ORDER BY excess_order_min DESC",
    "anomaly_episodes": "SELECT * EXCLUDE (node_list), array_to_string(node_list, ' ') AS nodes FROM anomaly_episodes",
    "stockout_clusters": "SELECT * FROM stockout_clusters",
    "change_point_results": "SELECT * FROM change_point_results ORDER BY node_id",
    "before_after": "SELECT * FROM before_after",
}


def run() -> None:
    cfg = load_config(PROJECT)
    findings = json.loads((OUT / "findings.json").read_text())
    con = open_db(read_only=True)
    try:
        data_quality(con)
        export_csv(con, KPI_EXPORTS, OUT / "kpi")
        workbook.build(con, cfg, OUT / "p1_fulfilment_kpis.xlsx")
        dashboard.build(con, findings, cfg, PROJECT / "docs" / "index.html")
        crosscheck.run(con, cfg)
        narrative.run(con, findings, cfg)
    finally:
        con.close()
