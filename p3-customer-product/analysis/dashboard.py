"""Project 3 dashboard: docs/index.html."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from shared.dashboard import MUTED, SEQ_BLUE, fig_html, page, section, series, style_fig, table_block, tile


def funnel_chart(overall: pd.DataFrame) -> go.Figure:
    s = series(0)
    fig = go.Figure(go.Bar(x=overall.share_of_visits * 100, y=overall.step.str.replace("_", " "), orientation="h",
                           meta=s["meta"], marker=dict(color=s["color"]),
                           customdata=overall[["sessions", "step_conversion"]].fillna(1),
                           hovertemplate="%{y}: %{customdata[0]:,} sessions<br>%{x:.1f}% of visits"
                                         "<br>step conversion %{customdata[1]:.1%}<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(xaxis_title="% of sessions reaching the step", showlegend=False)
    return style_fig(fig, 300)


def payment_daily(con) -> go.Figure:
    d = con.execute("""SELECT platform || ' ' || app_version AS segment, date_trunc('week', session_date) AS week,
                       sum(orders) / sum(payment_attempts) AS success, sum(payment_attempts) AS attempts
                       FROM funnel_daily_payment GROUP BY ALL HAVING sum(payment_attempts) >= 100 ORDER BY week""").df()
    fig = go.Figure()
    for slot, seg in enumerate(sorted(d.segment.unique())):
        g = d[d.segment == seg]
        s = series(slot)
        fig.add_trace(go.Scatter(x=g.week, y=g.success * 100, name=seg, mode="lines+markers", meta=s["meta"],
                                 line=dict(color=s["color"], width=2), marker=dict(size=5, color=s["color"]),
                                 hovertemplate=f"{seg}<br>week of %{{x|%d %b}}: %{{y:.1f}}%<extra></extra>"))
    fig.update_layout(yaxis_title="payment success (%)", hovermode="x unified")
    return style_fig(fig, 340)


def cohort_heatmap(con) -> go.Figure:
    c = con.execute("SELECT strftime(cohort_month, '%Y-%m') AS cohort, months_since_first, retention, cohort_size FROM cohort_retention").df()
    z = c.pivot(index="cohort", columns="months_since_first", values="retention") * 100
    fig = go.Figure(go.Heatmap(z=z.values, x=[f"M{k}" for k in z.columns], y=list(z.index), colorscale=SEQ_BLUE, xgap=2, ygap=2,
                               zmin=0, zmax=50, colorbar=dict(thickness=10),
                               hovertemplate="cohort %{y}, %{x}: %{z:.1f}% ordering<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(xaxis_title="months since first order (M0 = 100%, scale capped at 50%)")
    return style_fig(fig, 420)


def repeat_curve(rc: dict) -> go.Figure:
    s = series(0)
    x = sorted(int(k) for k in rc)
    fig = go.Figure(go.Scatter(x=x, y=[rc[str(k)] * 100 for k in x], mode="lines+markers", meta=s["meta"],
                               line=dict(color=s["color"], width=2), marker=dict(size=8, color=s["color"]),
                               hovertemplate="within %{x} days: %{y:.1f}%<extra></extra>"))
    fig.update_layout(xaxis_title="days after first order", yaxis_title="% with a second order", showlegend=False)
    return style_fig(fig, 320)


def drivers(model: list[dict]) -> go.Figure:
    m = pd.DataFrame(model)
    m = m[m.term != "log_first_basket"].sort_values("marginal_effect_pp")
    m["term"] = m.term.str.replace("first_order_issue", "problem on first order")
    s = series(0)
    fig = go.Figure(go.Scatter(x=m.marginal_effect_pp, y=m.term, mode="markers", meta=s["meta"], marker=dict(size=9, color=s["color"]),
                               error_x=dict(type="data", symmetric=False, array=m.ci_high_pp - m.marginal_effect_pp,
                                            arrayminus=m.marginal_effect_pp - m.ci_low_pp, thickness=2, width=0),
                               hovertemplate="%{y}: %{x:+.1f} pp<extra></extra>"))
    fig.add_vline(x=0, line=dict(color=MUTED, width=1))
    fig.update_layout(xaxis_title="effect on 90-day repeat rate (percentage points, 95% CI)", showlegend=False)
    return style_fig(fig, 320)


def rfm_chart(rfm: list[dict]) -> go.Figure:
    r = pd.DataFrame(rfm)
    fig = go.Figure()
    for slot, (col, label) in enumerate([("share_customers", "Share of customers"), ("share_margin", "Share of gross margin")]):
        s = series(slot)
        fig.add_trace(go.Bar(x=r.segment, y=r[col] * 100, name=label, meta=s["meta"], marker=dict(color=s["color"]),
                             hovertemplate=f"%{{x}}<br>{label}: %{{y:.1f}}%<extra></extra>"))
    fig.update_layout(barmode="group", yaxis_title="%")
    return style_fig(fig, 320)


def abc_matrix(abc: list[dict]) -> go.Figure:
    m = pd.DataFrame(abc).pivot(index="abc", columns="xyz", values="skus").reindex(index=list("ABC"), columns=list("XYZ")).fillna(0)
    share = pd.DataFrame(abc).pivot(index="abc", columns="xyz", values="revenue_share").reindex(index=list("ABC"), columns=list("XYZ")).fillna(0)
    text = [[f"{int(m.iloc[i, j])} SKUs<br>{share.iloc[i, j] * 100:.1f}% revenue" for j in range(3)] for i in range(3)]
    fig = go.Figure(go.Heatmap(z=m.values, x=list("XYZ"), y=list("ABC"), text=text, texttemplate="%{text}",
                               colorscale=[[0, "#eef5fd"], [1, "#86b6ef"]], textfont=dict(color="#0b0b0b"),
                               xgap=3, ygap=3, showscale=False, hovertemplate="%{y}%{x}: %{text}<extra></extra>"))
    fig.update_yaxes(autorange="reversed", title="ABC (revenue)")
    fig.update_xaxes(title="XYZ (demand variability)")
    return style_fig(fig, 320)


def waste_scatter(con, threshold: float) -> go.Figure:
    w = con.execute("SELECT node_id || ' ' || sku_id AS label, category, risk_score, waste_cost, avg_daily_sold FROM wastage_node_sku WHERE waste_cost > 0").df()
    s0, s1 = series(0), series(1)
    fig = go.Figure()
    for flag, s, name in [(False, s0, "below threshold"), (True, s1, "cover at or above shelf life")]:
        g = w[(w.risk_score >= threshold) == flag]
        fig.add_trace(go.Scatter(x=g.risk_score, y=g.waste_cost, mode="markers", name=name, meta=s["meta"], text=g.label,
                                 marker=dict(size=8, color=s["color"], line=dict(width=1, color="rgba(252,252,251,0.9)")),
                                 customdata=g[["category", "avg_daily_sold"]],
                                 hovertemplate="%{text} (%{customdata[0]})<br>risk %{x:.2f}<br>waste cost %{y:,.0f}"
                                               "<br>%{customdata[1]:.1f} units/day<extra></extra>"))
    fig.add_vline(x=threshold, line=dict(color=MUTED, dash="dot", width=1))
    fig.update_layout(xaxis=dict(title="days of cover / shelf life", type="log"), yaxis=dict(title="annual waste cost", type="log"))
    return style_fig(fig, 380)


def build(con, findings: dict, cfg: dict, out: Path) -> Path:
    f = findings
    d = f["funnel"]["dropoff"]
    ret = f["retention"]
    summary = {r["action"]: r for r in f["assortment"]["summary"]}
    conv = {r["step"]: r for r in f["funnel"]["overall"]}
    tiles = [
        tile("Ordering customers", f"{ret['customers']:,}", "first orders in the year"),
        tile("Repeat within 90 days", f"{ret['repeat_curve']['90'] * 100:.1f}%", f"{ret['repeat_curve']['30'] * 100:.1f}% within 30 days"),
        tile("Session conversion", f"{conv['order_placed']['share_of_visits'] * 100:.1f}%", "visit to order"),
        tile("Funnel fault", f"{d['platform']} {d['app_version']}" if d else "none",
             f"payment success {d['rate'] * 100:.0f}% vs {d['others_rate'] * 100:.0f}%; ~{d['lost_orders']:,.0f} orders lost" if d else ""),
        tile("Perishable waste", f"{f['wastage']['total_cost']:,.0f}", f"{f['wastage']['waste_rate'] * 100:.1f}% of units received"),
        tile("Assortment upside", f"{summary['add']['impact_low']:,.0f} to {summary['add']['impact_high']:,.0f}" if "add" in summary else "n/a",
             f"annual margin from {summary['add']['recs'] if 'add' in summary else 0} add recommendations"),
    ]
    recs = con.execute("""SELECT r.node_id, r.action, r.sku_id, r.category, round(r.impact_low) AS impact_low,
                          round(r.impact_high) AS impact_high, r.impact_metric FROM assortment_recommendations r
                          ORDER BY abs(r.impact_high) DESC""").df()
    per_node = con.execute("""PIVOT (SELECT node_id, action, count(*) AS n FROM assortment_recommendations GROUP BY ALL)
                              ON action USING first(n) ORDER BY node_id""").df().fillna(0)
    aff = pd.DataFrame(f["affinity"])[["sku_a", "category_a", "sku_b", "category_b", "together", "support", "confidence_a_to_b",
                                         "confidence_b_to_a", "lift"]]
    sections = [
        section("Checkout funnel", "Share of sessions reaching each step (all platforms).", fig_html(funnel_chart(pd.DataFrame(f["funnel"]["overall"])), "funnel")),
        section("Payment success by platform and app version",
                "Weekly share of payment attempts that become orders. A step change isolated to one app version points to a release fault.",
                fig_html(payment_daily(con), "payment")),
        section("Cohort retention", "Share of each first-order cohort ordering again in each later month.", fig_html(cohort_heatmap(con), "cohorts")),
        section("How fast customers come back", "Second-order rate by days since the first order (customers observable that long).",
                fig_html(repeat_curve(ret["repeat_curve"]), "repeat")),
        section("Why customers retain", "Logistic model of 90-day repeat; average marginal effects against organic acquisition and iOS.",
                fig_html(drivers(ret["model"]), "drivers")),
        section("RFM segments", "Customers scored on recency, frequency and margin (NTILE quintiles) as of the year end.",
                fig_html(rfm_chart(f["rfm"]), "rfm")),
        section("ABC-XYZ", "Revenue concentration by demand predictability (median node-level weekly CV).", fig_html(abc_matrix(f["abc_xyz"]), "abc")),
        section("Basket affinity", "Pairs bought together far more often than chance (lift), with at least the minimum co-occurrence.",
                table_block("aff", aff, ["category_a", "category_b"])),
        section("Perishable wastage risk", "Each dot is a node-SKU. Right of the line, the shelf holds more than can sell before expiry.",
                fig_html(waste_scatter(con, cfg["analysis"]["wastage_risk_threshold"]), "waste")),
        section("Assortment recommendations by node", "Add, drop or reduce depth with an impact range. Filter by node and action.",
                table_block("pernode", per_node, []) + table_block("recs", recs, ["node_id", "action", "category"])),
    ]
    html = page(title="Customer, product and inventory analytics",
                subtitle="Which customers retain and why, which products deserve more space, and how each node's assortment should change.",
                disclosure=("<strong>Simulated data.</strong> Customers, sessions, baskets and stock are produced by a seeded synthetic generator; "
                            "this is not real company data. The same tables are exported as CSV and as an Excel workbook with a "
                            "formula-driven ABC-XYZ and wastage model."),
                tiles=tiles, sections=sections, footer="Built by make all from SQL in p3-customer-product/sql.")
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
