"""Collect the analysis results into outputs/findings.json, the single source for every number in prose."""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
FINDINGS = PROJECT / "outputs" / "findings.json"


def _clean(v):
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.date().isoformat() if isinstance(v, (pd.Timestamp, datetime)) else v.isoformat()
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return None if math.isnan(v) else round(float(v), 6)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (list, tuple, np.ndarray)):
        return [_clean(x) for x in v]
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    return v


def _records(df: pd.DataFrame) -> list[dict]:
    return [_clean(r) for r in df.to_dict("records")]


def collect(con, cfg: dict) -> dict:
    q = lambda sql, p=None: con.execute(sql, p or []).df()  # noqa: E731
    net = q("SELECT * FROM kpi_delivery_node WHERE node_id = 'ALL'").iloc[0]
    defects = q("SELECT * FROM kpi_defects_network")
    any_defect = defects[defects.defect_type.isna()].iloc[0]
    inv = q("""SELECT sum(units_fulfilled) / sum(units_ordered) AS fill_rate, sum(short_value) AS short_value
               FROM kpi_fill_node_category""").iloc[0]
    riders = q("SELECT * FROM kpi_riders_node WHERE node_id = 'ALL'").iloc[0]
    nodes = q("""SELECT d.node_id, d.pct_within_sla, d.p90_delivery_min, d.orders_placed
                 FROM kpi_delivery_node d WHERE node_id <> 'ALL' ORDER BY pct_within_sla""")

    network = {
        "sla_minutes": cfg["ops"]["sla_minutes"], "days": cfg["sim"]["days"],
        "nodes": int(len(nodes)), "orders_placed": int(net.orders_placed), "orders_timed": int(net.orders_timed),
        "pct_within_sla": net.pct_within_sla, "p50_delivery_min": net.p50_delivery_min,
        "p90_delivery_min": net.p90_delivery_min, "cancel_rate": net.cancel_rate,
        "late_orders": int(net.orders_timed - net.orders_within_sla),
        "defect_rate_any": any_defect.defect_rate, "refund_total": any_defect.refund_amount,
        "refund_pct_gmv": any_defect.refund_pct_gmv,
        "fill_rate": inv.fill_rate, "short_value": inv.short_value,
        "rider_utilisation": riders.utilisation, "orders_per_rider_hour": riders.orders_per_rider_hour,
        "worst_node": nodes.iloc[0].node_id, "worst_node_pct_within_sla": nodes.iloc[0].pct_within_sla,
        "best_node": nodes.iloc[-1].node_id, "best_node_pct_within_sla": nodes.iloc[-1].pct_within_sla,
    }
    defect_types = _records(defects[defects.defect_type.notna()].sort_values("refund_amount", ascending=False))

    chronic_rows = q("SELECT * FROM anomaly_chronic ORDER BY node_id, cell_hour")
    impact = q("SELECT * FROM impact_chronic").set_index("node_id")
    chronic = []
    for node, g in chronic_rows.groupby("node_id", sort=True):
        imp = impact.loc[node]
        # staffing gap: pickers needed to bring orders per picker down to the peer level in those hours
        staff = con.execute("""
            SELECT avg(pickers_rostered) AS pickers, avg(orders_placed) AS orders
            FROM node_hour_cells WHERE node_id = ? AND cell_hour IN (SELECT unnest(?))""",
            [node, g.cell_hour.tolist()]).fetchone()
        peer_opp = g.peer_orders_per_picker.mean()
        chronic.append(_clean({
            "node_id": node, "hours": g.cell_hour.tolist(), "driver_stage": g.driver_stage.mode().iloc[0],
            "flagged_day_share": g.flagged_day_share.mean(),
            "orders_per_picker": g.orders_per_picker.mean(), "peer_orders_per_picker": g.peer_orders_per_picker.mean(),
            "pick_excess_min": g.pick_excess_min.mean(), "wait_excess_min": g.wait_excess_min.mean(),
            "travel_excess_min": g.travel_excess_min.mean(),
            "orders_timed": int(imp.orders_timed), "late_orders": int(imp.late_orders),
            "late_rate": imp.late_rate, "peer_late_rate": imp.peer_late_rate,
            "recoverable_late_orders": int(imp.recoverable_late_orders),
            "recoverable_share_of_network_late": imp.recoverable_late_orders / network["late_orders"],
            "pickers_rostered": staff[0], "orders_per_hour": staff[1],
            "extra_pickers_per_hour": max(0.0, staff[1] / peer_opp - staff[0]),
            "extra_picker_hours_per_week": max(0.0, staff[1] / peer_opp - staff[0]) * len(g) * 7,
        }))

    episodes = q("SELECT * FROM anomaly_episodes ORDER BY excess_order_min DESC")
    episodes["node_list"] = episodes.node_list.apply(list)
    totals = episodes[["pick_excess_min", "wait_excess_min", "travel_excess_min"]].clip(lower=0)
    episodes["driver_share"] = totals.max(axis=1) / totals.sum(axis=1)

    clusters = q("SELECT * FROM stockout_clusters ORDER BY short_value DESC")
    cluster_refunds = q("""
        SELECT r.node_id, r.category, sum(d.refund_amount) AS missing_refunds, count(*) AS missing_claims
        FROM stockout_node_sku r JOIN defects d ON d.sku_id = r.sku_id
        JOIN orders o ON o.order_id = d.order_id AND o.node_id = r.node_id
        WHERE r.repeat_stockout AND d.defect_type = 'missing_item' GROUP BY ALL""")
    clusters = clusters.merge(cluster_refunds, on=["node_id", "category"], how="left")
    total_missing = defects.loc[defects.defect_type == "missing_item", "refund_amount"].iloc[0]
    clusters["share_of_missing_refunds"] = clusters.missing_refunds / total_missing

    cp = q("SELECT * FROM change_point_results ORDER BY node_id")
    ba = q("SELECT * FROM before_after")
    changes = []
    for r in cp[cp.detected].itertuples():
        metrics = {m.metric: _clean(m._asdict()) for m in ba[ba.node_id == r.node_id].itertuples(index=False)}
        changes.append(_clean({"node_id": r.node_id, "split_date": r.split_date, "welch_t": r.welch_t,
                               "p_value": r.p_value, "shift_min": r.shift_min, "shift_rel": r.shift_rel,
                               "metrics": metrics}))

    dq = q("SELECT * FROM dq_report")
    flags = q("SELECT flag_type, count(*) AS n FROM anomaly_flags GROUP BY 1")
    return _clean({
        "network": network,
        "defect_types": defect_types,
        "chronic": chronic,
        "episodes": _records(episodes),
        "anomaly_counts": {
            "cells_scored": int(q("SELECT count(*) AS n FROM anomaly_scores").n.iloc[0]),
            "cells_flagged": int(flags.n.sum()),
            "by_type": dict(zip(flags.flag_type, flags.n.astype(int))),
            "incidents": int(q("SELECT count(*) AS n FROM anomaly_incidents").n.iloc[0]),
        },
        "stockout_clusters": _records(clusters),
        "change_points": changes,
        "change_point_scan": _records(cp),
        "data_quality": _records(dq),
    })


def run(con, cfg: dict) -> dict:
    findings = collect(con, cfg)
    FINDINGS.parent.mkdir(exist_ok=True)
    FINDINGS.write_text(json.dumps(findings, indent=2, sort_keys=True))
    return findings
