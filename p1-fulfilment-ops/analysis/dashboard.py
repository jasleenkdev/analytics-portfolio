"""Project 1 dashboard: docs/index.html."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from shared.dashboard import (MUTED, SEQ_BLUE, fig_html, page, section, series, style_fig, table_block, tile)

STAGES = [("mean_pick_min", "Picking", 0), ("mean_rider_wait_min", "Rider wait", 1), ("mean_travel_min", "Travel", 2)]


def heatmap(con) -> go.Figure:
    prof = con.execute("SELECT * FROM kpi_node_hour_profile").df()
    metrics = [("late_rate", "Late rate (% of orders over SLA)", lambda d: (1 - d.pct_within_sla) * 100, "%{z:.1f}%"),
               ("mean_pick_min", "Mean pick minutes", lambda d: d.mean_pick_min, "%{z:.1f} min"),
               ("mean_rider_wait_min", "Mean rider wait minutes", lambda d: d.mean_rider_wait_min, "%{z:.1f} min"),
               ("p90", "P90 delivery minutes", lambda d: d.p90_delivery_min, "%{z:.1f} min")]
    fig = go.Figure()
    for i, (_, label, fn, fmt) in enumerate(metrics):
        z = prof.assign(v=fn(prof)).pivot(index="node_id", columns="order_hour", values="v")
        fig.add_trace(go.Heatmap(
            z=z.values, x=[f"{h:02d}:00" for h in z.columns], y=list(z.index), colorscale=SEQ_BLUE, visible=i == 0,
            xgap=2, ygap=2, colorbar=dict(thickness=10, title=dict(text="")),
            hovertemplate=f"Node %{{y}} at %{{x}}<br>{label}: {fmt}<extra></extra>", name=label))
    buttons = [dict(label=label, method="update",
                    args=[{"visible": [j == i for j in range(len(metrics))]}])
               for i, (_, label, _, _) in enumerate(metrics)]
    fig.update_layout(updatemenus=[dict(buttons=buttons, direction="down", x=0, y=1.16, xanchor="left", showactive=True)])
    fig.update_yaxes(autorange="reversed")
    return style_fig(fig, 430)


def decomposition(con) -> go.Figure:
    d = con.execute("SELECT * FROM kpi_delay_decomposition_node ORDER BY mean_delivery_min").df()
    fig = go.Figure()
    for col, label, slot in STAGES:
        s = series(slot)
        fig.add_trace(go.Bar(y=d.node_id, x=d[col], name=label, orientation="h", meta=s["meta"],
                             marker=dict(color=s["color"], line=dict(width=1, color="rgba(252,252,251,1)")),
                             hovertemplate=f"%{{y}}<br>{label}: %{{x:.1f}} min<extra></extra>"))
    fig.update_layout(barmode="stack", xaxis_title="mean minutes per order (placed to delivered)")
    return style_fig(fig, 420)


def sla_trend(con, sla: int) -> go.Figure:
    d = con.execute("SELECT * FROM kpi_network_daily ORDER BY order_date").df()
    fig = go.Figure()
    s0 = series(0)
    fig.add_trace(go.Scatter(x=d.order_date, y=d.pct_within_sla * 100, name="Daily", mode="lines",
                             line=dict(color=MUTED, width=1), hovertemplate="%{x|%a %d %b}: %{y:.1f}%<extra>daily</extra>"))
    fig.add_trace(go.Scatter(x=d.order_date, y=d.pct_within_sla_7d * 100, name="7-day rolling", mode="lines",
                             meta=s0["meta"], line=dict(color=s0["color"], width=2),
                             hovertemplate="%{x|%a %d %b}: %{y:.1f}%<extra>7-day</extra>"))
    fig.update_layout(yaxis_title=f"% of orders within {sla} min", hovermode="x unified")
    return style_fig(fig, 340)


def before_after(con, change: dict) -> go.Figure:
    d = con.execute("SELECT * FROM node_vs_rest_daily WHERE node_id = ? ORDER BY order_date", [change["node_id"]]).df()
    fig = go.Figure()
    s0, s1 = series(0), series(1)
    fig.add_trace(go.Scatter(x=d.order_date, y=d.median_pick_min, name=change["node_id"], mode="lines",
                             meta=s0["meta"], line=dict(color=s0["color"], width=2)))
    fig.add_trace(go.Scatter(x=d.order_date, y=d.rest_median_pick_min, name="Rest of network", mode="lines",
                             meta=s1["meta"], line=dict(color=s1["color"], width=2)))
    fig.add_vline(x=pd.Timestamp(change["split_date"]).timestamp() * 1000, line=dict(color=MUTED, dash="dot", width=1),
                  annotation_text="detected change", annotation_position="top left")
    fig.update_layout(yaxis_title="daily median pick minutes", hovermode="x unified")
    return style_fig(fig, 340)


def stockouts(con) -> go.Figure:
    d = con.execute("""SELECT node_id || ' ' || category AS label, avg(stockout_rate) AS stockout_rate
                       FROM stockout_node_sku GROUP BY node_id, category ORDER BY stockout_rate DESC LIMIT 12""").df()
    s = series(0)
    fig = go.Figure(go.Bar(x=d.stockout_rate * 100, y=d.label, orientation="h", meta=s["meta"],
                           marker=dict(color=s["color"]), hovertemplate="%{y}: %{x:.1f}% of open hours at zero<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(xaxis_title="share of operating hours with zero stock (tracked SKUs)", showlegend=False)
    return style_fig(fig, 380)


def build(con, findings: dict, cfg: dict, out: Path) -> Path:
    n = findings["network"]
    sla = n["sla_minutes"]
    tiles = [
        tile("Orders", f"{n['orders_placed']:,}", f"{n['days']} days, {n['nodes']} nodes"),
        tile(f"Within {sla}-min SLA", f"{n['pct_within_sla'] * 100:.1f}%",
             f"best {n['best_node']} {n['best_node_pct_within_sla'] * 100:.1f}%, worst {n['worst_node']} {n['worst_node_pct_within_sla'] * 100:.1f}%"),
        tile("P50 / P90 delivery", f"{n['p50_delivery_min']:.1f} / {n['p90_delivery_min']:.1f} min", "placed to delivered"),
        tile("Orders with a defect", f"{n['defect_rate_any'] * 100:.1f}%", f"refunds {n['refund_pct_gmv'] * 100:.2f}% of GMV"),
        tile("Fill rate", f"{n['fill_rate'] * 100:.2f}%", "units fulfilled / ordered"),
        tile("Rider utilisation", f"{n['rider_utilisation'] * 100:.0f}%", f"{n['orders_per_rider_hour']:.2f} orders per rider-hour"),
    ]
    anomalies = con.execute("""
        SELECT node_id, hour_ts AS hour, flag_type, driver_stage, round(z_temporal, 2) AS z_temporal,
               round(z_peer, 2) AS z_peer, orders_timed AS orders, round(mean_delivery_min, 1) AS mean_delivery_min,
               round(late_rate * 100, 1) AS late_pct, round(pick_excess, 1) AS pick_excess_min,
               round(wait_excess, 1) AS wait_excess_min, round(travel_excess, 1) AS travel_excess_min,
               round(orders_per_picker, 1) AS orders_per_picker, riders_online, weather,
               EXISTS (SELECT 1 FROM anomaly_chronic c WHERE c.node_id = d.node_id AND c.cell_hour = d.cell_hour) AS chronic
        FROM anomaly_drilldown d ORDER BY excess_order_min DESC""").df()
    anomalies["chronic"] = anomalies.chronic.map({True: "yes", False: "no"})
    episodes = con.execute("""
        SELECT start_date, end_date, days, driver_stage, array_to_string(node_list, ', ') AS nodes, flagged_hours,
               round(excess_order_min) AS excess_order_min, round(wait_excess_min, 1) AS wait_excess_min,
               round(pick_excess_min, 1) AS pick_excess_min, round(travel_excess_min, 1) AS travel_excess_min,
               round(orders_vs_history * 100) AS orders_vs_history_pct, round(riders_online_vs_history * 100) AS riders_vs_history_pct,
               weather
        FROM anomaly_episodes ORDER BY excess_order_min DESC""").df()
    clusters = con.execute("""SELECT node_id, category, repeat_skus, round(stockout_rate * 100, 1) AS stockout_pct,
                              round(opening_cover_days, 2) AS opening_cover_days,
                              round(other_nodes_cover_days, 2) AS same_skus_other_nodes_cover,
                              round(mean_first_zero_hour, 1) AS mean_hour_shelf_empties, units_short,
                              round(short_value, 2) AS short_value FROM stockout_clusters""").df()

    sections = [
        section("Where and when the SLA breaks",
                "Node x hour-of-day profile over the whole period. Switch the metric to separate slow picking from rider shortage.",
                fig_html(heatmap(con), "heatmap")),
        section("Delay decomposition by node",
                                        "Delivery time splits exactly into picking, waiting for a rider and travel.",
                                        fig_html(decomposition(con), "decomp")),
        section("Network SLA trend", "Share of orders delivered within the SLA; the rolling line is a ratio of 7-day counts.",
                  fig_html(sla_trend(con, sla), "trend")),
        section("Anomaly episodes",
                "Acute network events: two or more nodes with sustained flags on the same day and the same driving stage, merged across consecutive days.",
                table_block("episodes", episodes, ["driver_stage", "weather"])),
        section("Flagged node-hours",
                "Every node-hour whose delivery time was abnormal against its own history (temporal) or the other nodes (peer). "
                "Excess minutes are measured against the baseline that triggered the flag. Click a header to sort.",
                table_block("anomalies", anomalies, ["node_id", "flag_type", "driver_stage", "chronic", "weather"])),
    ]
    if findings["change_points"]:
        c = findings["change_points"][0]
        sections.append(section(f"Step change at {c['node_id']}",
                                f"Detected from data on {c['split_date']} (permutation p = {c['p_value']:.3f}).",
                                fig_html(before_after(con, c), "beforeafter")))
    sections.append(section("Repeat stockouts",
                            "Tracked node-SKUs that hit zero on at least half of all days, grouped by node and category, "
                            "with opening cover against ordered demand.",
                            fig_html(stockouts(con), "stockouts") + table_block("clusters", clusters, ["node_id", "category"])))

    html = page(
        title="Fulfilment and delivery operations",
        subtitle="Where and why the delivery SLA is missed, and what operations should change.",
        disclosure=("<strong>Simulated data.</strong> Every number is produced by a seeded synthetic generator "
                    "(12 fulfilment nodes, 90 days, about 400k orders). It is not real company data. "
                    "The same KPIs are exported as CSV and as an Excel workbook with live formulas."),
        tiles=tiles, sections=sections,
        footer="Built by make all from SQL in p1-fulfilment-ops/sql. Hover any chart for values; tables filter and sort.",
    )
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
