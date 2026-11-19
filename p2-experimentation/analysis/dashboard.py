"""Project 2 dashboard: docs/index.html."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from shared.dashboard import MUTED, fig_html, page, section, series, style_fig, table_block, tile

LABELS = {"contribution": "Contribution per user", "orders": "Orders per user", "gmv": "GMV per user",
          "converted": "Users ordering", "fee_revenue": "Delivery fee revenue per user",
          "product_margin": "Product margin per user", "gmv_per_order": "Basket value per order",
          "contribution_per_order": "Contribution per order", "high_margin_share": "High-margin basket share",
          "free_delivery_share": "Free-delivery order share"}
PILOT_LABELS = {"cost_per_order": "Rider cost per order", "mean_delivery_min": "Mean delivery minutes",
                "defect_rate": "Defect rate", "pct_within_sla": "% within SLA"}


def forest(rows: pd.DataFrame, label_col: str, title_x: str, height: int = 380) -> go.Figure:
    s = series(0)
    fig = go.Figure(go.Scatter(
        x=rows.rel_diff * 100, y=rows[label_col], mode="markers", meta=s["meta"],
        marker=dict(color=s["color"], size=9),
        error_x=dict(type="data", symmetric=False, array=(rows.rel_ci_high - rows.rel_diff) * 100,
                     arrayminus=(rows.rel_diff - rows.rel_ci_low) * 100, color=s["color"], thickness=2, width=0),
        hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
    fig.add_vline(x=0, line=dict(color=MUTED, width=1))
    fig.update_layout(xaxis_title=title_x, showlegend=False)
    fig.update_yaxes(autorange="reversed")
    return style_fig(fig, height)


def novelty(nov: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for slot, (m, label) in enumerate([("orders", "Orders per user"), ("contribution", "Contribution per user")]):
        d = nov[nov.metric == m]
        s = series(slot)
        fig.add_trace(go.Scatter(x=d.week, y=d.rel_diff * 100, name=label, mode="lines+markers", meta=s["meta"],
                                 line=dict(color=s["color"], width=2), marker=dict(size=9, color=s["color"]),
                                 error_y=dict(type="data", symmetric=False, array=(d.rel_ci_high - d.rel_diff) * 100,
                                              arrayminus=(d.rel_diff - d.rel_ci_low) * 100, thickness=1.5, width=4),
                                 hovertemplate=f"Week %{{x}}<br>{label}: %{{y:.1f}}%<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=MUTED, width=1))
    fig.update_layout(xaxis=dict(title="week since assignment", dtick=1), yaxis_title="treatment vs control (%)")
    return style_fig(fig, 340)


def srm_chart(daily: pd.DataFrame) -> go.Figure:
    d = daily.assign(share=lambda x: x.n_treatment / (x.n_treatment + x.n_control) * 100)
    s0, s1 = series(0), series(1)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=d.assign_date, y=d.share, name="Treatment share", meta=s0["meta"],
                         marker=dict(color=[s1["color"] if f else s0["color"] for f in d.flagged]),
                         customdata=d[["n_control", "n_treatment", "p_value"]],
                         hovertemplate="%{x}<br>treatment %{y:.1f}%<br>control %{customdata[0]:,} / treatment %{customdata[1]:,}"
                                       "<br>p = %{customdata[2]:.2g}<extra></extra>"))
    fig.add_hline(y=50, line=dict(color=MUTED, dash="dot", width=1), annotation_text="designed 50%")
    fig.update_layout(yaxis=dict(title="treatment share of assignments (%)", range=[40, 62]), showlegend=False)
    return style_fig(fig, 300)


def basket_hist(hist: pd.DataFrame, thresholds: dict) -> go.Figure:
    fig = go.Figure()
    for slot, v in enumerate(["control", "treatment"]):
        d = hist[hist.variant == v]
        share = d.orders / d.orders.sum() * 100
        s = series(slot)
        fig.add_trace(go.Bar(x=d.basket_bin + 1, y=share, name=v.capitalize(), meta=s["meta"],
                             marker=dict(color=s["color"]), hovertemplate=f"{v}: basket %{{x}} ± 1<br>%{{y:.2f}}% of orders<extra></extra>"))
    for v, t in thresholds.items():
        fig.add_vline(x=t, line=dict(color=MUTED, dash="dot", width=1), annotation_text=f"{v} threshold")
    fig.update_layout(barmode="group", xaxis_title="basket value", yaxis_title="% of the arm's orders")
    return style_fig(fig, 340)


def pilot_weekly(weekly: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    metrics = list(PILOT_LABELS)
    for i, m in enumerate(metrics):
        for slot, grp in enumerate(["treatment", "control"]):
            d = weekly[weekly.pilot_group == grp]
            y = d[m] * (100 if m in ("defect_rate", "pct_within_sla") else 1)
            s = series(slot)
            fig.add_trace(go.Scatter(x=d.rel_week, y=y, name=f"{'Pilot' if grp == 'treatment' else 'Control'} nodes",
                                     mode="lines+markers", visible=i == 0, meta=s["meta"],
                                     line=dict(color=s["color"], width=2), marker=dict(size=6, color=s["color"]),
                                     hovertemplate=f"week %{{x}}<br>{PILOT_LABELS[m]}: %{{y:.2f}}<extra></extra>"))
    fig.add_vline(x=-0.5, line=dict(color=MUTED, dash="dot", width=1), annotation_text="pilot starts")
    buttons = [dict(label=PILOT_LABELS[m], method="update",
                    args=[{"visible": [j // 2 == i for j in range(2 * len(metrics))]}]) for i, m in enumerate(metrics)]
    fig.update_layout(updatemenus=[dict(buttons=buttons, x=0, y=1.18, xanchor="left")],
                      xaxis_title="weeks relative to pilot start", hovermode="x unified")
    style_fig(fig, 360)
    fig.update_layout(legend=dict(x=1, xanchor="right", y=1.12))
    return fig


def event_study(es: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    metrics = list(PILOT_LABELS)
    s = series(0)
    for i, m in enumerate(metrics):
        d = es[es.metric == m].sort_values("rel_week")
        k = 100 if m in ("defect_rate", "pct_within_sla") else 1
        fig.add_trace(go.Scatter(x=d.rel_week, y=d.estimate * k, mode="markers", visible=i == 0, meta=s["meta"],
                                 marker=dict(size=8, color=s["color"]), name=PILOT_LABELS[m],
                                 error_y=dict(type="data", symmetric=False, array=(d.ci_high - d.estimate) * k,
                                              arrayminus=(d.estimate - d.ci_low) * k, thickness=1.5, width=0),
                                 hovertemplate="week %{x}: %{y:.3f}<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=MUTED, width=1))
    fig.add_vline(x=-0.5, line=dict(color=MUTED, dash="dot", width=1))
    buttons = [dict(label=PILOT_LABELS[m], method="update", args=[{"visible": [j == i for j in range(len(metrics))]}])
               for i, m in enumerate(metrics)]
    fig.update_layout(updatemenus=[dict(buttons=buttons, x=0, y=1.18, xanchor="left")], showlegend=False,
                      xaxis_title="weeks relative to pilot start (week -1 = reference)",
                      yaxis_title="pilot minus control, vs week -1")
    return style_fig(fig, 340)


def build(con, findings: dict, cfg: dict, out: Path) -> Path:
    p, q = findings["promo"], findings["pilot"]
    res = pd.DataFrame(p["results"])
    primary = res[(res.metric == "contribution") & (res.method == "CUPED")].iloc[0]
    orders = res[(res.metric == "orders") & (res.method == "CUPED")].iloc[0]
    did = pd.DataFrame(q["did"]).set_index("metric")
    tiles = [
        tile("Promotion call", p["decision"], f"threshold {p['thresholds']['control']:.0f} to {p['thresholds']['treatment']:.0f}"),
        tile("Contribution per user", f"{primary.rel_diff * 100:+.1f}%",
             f"95% CI {primary.rel_ci_low * 100:+.1f}% to {primary.rel_ci_high * 100:+.1f}% (CUPED)"),
        tile("Orders per user", f"{orders.rel_diff * 100:+.1f}%", f"break-even needs {p['breakeven_order_lift'] * 100:+.0f}%"),
        tile("Sample ratio", "mismatch" if p["srm"]["detected"] else "ok",
             f"{len(p['srm']['flagged_dates'])} day(s) excluded; p after = {p['srm']['after_exclusion_p']:.2f}"),
        tile("Pilot call", q["decision"].split(":")[0], f"{q['treated_nodes']} pilot vs {q['control_nodes']} control nodes"),
        tile("Rider cost per order", f"{did.loc['cost_per_order', 'rel_estimate'] * 100:+.1f}%",
             f"defects {q['guardrails']['defect_rate']['estimate_pp']:+.2f} pp (tolerance {q['guardrails']['defect_rate']['tolerance_pp']} pp)"),
    ]
    main = res[(res.population == "analysis") & ((res.method != "difference in means") | ~res.metric.isin(["contribution", "orders", "gmv"]))].copy()
    main["label"] = main.metric.map(LABELS) + main.method.map(lambda m: " (CUPED)" if m == "CUPED" else "")
    seg = pd.DataFrame(p["segments"])
    seg_c = seg[seg.metric == "orders"].assign(label=lambda d: d.dimension + ": " + d.segment)
    seg_tbl = seg.assign(rel_diff_pct=(seg.rel_diff * 100).round(2), ci_pct=lambda d: (d.rel_ci_low * 100).round(1).astype(str)
                         + " to " + (d.rel_ci_high * 100).round(1).astype(str))[
        ["metric", "dimension", "segment", "n_control", "n_treatment", "rel_diff_pct", "ci_pct", "p_value", "p_adjusted", "significant_adjusted"]]
    seg_tbl["significant_adjusted"] = seg_tbl.significant_adjusted.map({True: "yes", False: "no"})
    inter = pd.DataFrame(p["interactions"]).assign(significant_adjusted=lambda d: d.significant_adjusted.map({True: "yes", False: "no"}))
    daily = pd.DataFrame(p["srm_daily"])
    did_tbl = did.reset_index()[["metric", "estimate", "ci_low", "ci_high", "rel_estimate", "p_value", "pre_trend_p",
                                 "pre_trend_joint_p", "placebo_estimate", "placebo_p"]]
    hist = con.execute("SELECT * FROM exp_basket_hist").df()
    sections = [
        section("Promotion: effect on every metric",
                "Treatment minus control as % of control, with 95% CIs. Users from the assignment day that failed the sample-ratio check are excluded from both arms.",
                fig_html(forest(main, "label", "treatment vs control (%)", 420), "forest")),
        section("Novelty: the order lift fades, the margin loss does not",
                "Effect by week since each user's assignment.", fig_html(novelty(pd.DataFrame(p["novelty"])), "novelty")),
        section("Sample-ratio check by assignment day",
                "Share of each day's assignments that went to treatment; the highlighted day fails the per-day test.",
                fig_html(srm_chart(daily), "srm")),
        section("Baskets bunch above the new threshold",
                "Order basket value distribution by arm (2-unit bins).", fig_html(basket_hist(hist, p["thresholds"]), "baskets")),
        section("Segments (orders per user, CUPED)",
                "Per-segment effects; the table adds contribution, Holm-adjusted p-values and the interaction tests that ask whether segments truly differ.",
                fig_html(forest(seg_c, "label", "orders lift (%)", 420), "segments")
                + table_block("segtable", seg_tbl, ["metric", "dimension", "significant_adjusted"])
                + "<p class='lede' style='margin-top:12px'>Interaction tests (does the effect differ across the dimension?)</p>"
                + table_block("inter", inter, ["metric"])),
        section("Rider-batching pilot: weekly trends",
                "Order-weighted weekly means for pilot and control nodes; switch the metric to see the guardrails.",
                fig_html(pilot_weekly(con.execute("SELECT * FROM pilot_weekly").df()), "pilotweekly")),
        section("Pilot event study",
                "Week-by-week difference between pilot and control nodes relative to the week before the start, with node and date fixed effects.",
                fig_html(event_study(con.execute("SELECT * FROM pilot_event_study").df()), "eventstudy")),
        section("Pilot difference-in-differences", "Two-way fixed effects, node-clustered 95% CIs, pre-trend and placebo checks.",
                table_block("didtable", did_tbl, [])),
    ]
    html = page(
        title="Experimentation and pilot evaluation",
        subtitle="Should we launch a lower free-delivery threshold, and should we scale rider batching?",
        disclosure=("<strong>Simulated data.</strong> Users, orders and the pilot panel are produced by a seeded synthetic generator; "
                    "this is not real company data. The same statistics are exported as CSV and as an Excel workbook with live formulas."),
        tiles=tiles, sections=sections,
        footer="Built by make all from SQL in p2-experimentation/sql and statistics in analysis/stats.py.")
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
