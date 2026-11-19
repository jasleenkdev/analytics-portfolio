"""Run the experiment and pilot readouts and collect them into outputs/findings.json."""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from analysis import stats as st

PROJECT = Path(__file__).resolve().parents[1]
FINDINGS = PROJECT / "outputs" / "findings.json"
USER_METRICS = ["contribution", "orders", "gmv", "converted", "fee_revenue", "product_margin"]
COVARIATE = {"contribution": "pre_contribution", "orders": "pre_orders", "gmv": "pre_gmv"}
RATIOS = {"gmv_per_order": ("gmv", "orders"), "contribution_per_order": ("contribution", "orders"),
          "high_margin_share": ("high_margin_orders", "orders"), "free_delivery_share": ("free_delivery_orders", "orders")}
PILOT_METRICS = ["cost_per_order", "mean_delivery_min", "defect_rate", "pct_within_sla"]


def _clean(v):
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return None if math.isnan(v) else round(float(v), 6)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    return v


def _save(con, name: str, df: pd.DataFrame) -> None:
    con.register("tmp_df", df)
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp_df")
    con.unregister("tmp_df")


def _split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    return df[df.variant == "treatment"], df[df.variant == "control"]


def srm(con, cfg) -> dict:
    a = cfg["analysis"]
    daily = con.execute("SELECT * FROM dq_assignment_daily ORDER BY assign_date").df()
    daily["p_value"] = [st.srm_test(r.n_control, r.n_treatment) for r in daily.itertuples()]
    # Bonferroni across days: a single day is flagged only if it fails the strict threshold after correction
    daily["flagged"] = daily.p_value < a["srm_alpha"] / len(daily)
    overall_p = st.srm_test(daily.n_control.sum(), daily.n_treatment.sum())
    kept = daily[~daily.flagged] if overall_p < a["srm_alpha"] else daily
    return {"overall_p": overall_p, "overall_control": int(daily.n_control.sum()),
            "overall_treatment": int(daily.n_treatment.sum()), "detected": overall_p < a["srm_alpha"],
            "flagged_dates": [d for d in daily.loc[daily.flagged, "assign_date"]],
            "after_exclusion_p": st.srm_test(kept.n_control.sum(), kept.n_treatment.sum()),
            "after_exclusion_control": int(kept.n_control.sum()), "after_exclusion_treatment": int(kept.n_treatment.sum()),
            "daily": daily}


def promo(con, cfg) -> dict:
    a, promo_cfg = cfg["analysis"], cfg["promo"]
    alpha = a["alpha"]
    s = srm(con, cfg)
    users = con.execute("SELECT * FROM exp_user_metrics").df()
    users["assign_date"] = pd.to_datetime(users.assign_date)
    excluded = pd.to_datetime(pd.Series(s["flagged_dates"], dtype="object"))
    pop = users[~users.assign_date.isin(excluded)].copy()
    t, c = _split(pop)

    rows = []
    for m in USER_METRICS:
        rows.append({"population": "analysis", "metric": m, "method": "difference in means", **st.welch(t[m].values, c[m].values, alpha)})
        if m in COVARIATE:
            y_adj, theta, vr = st.cuped(pop[m].values.astype(float), pop[COVARIATE[m]].values.astype(float))
            adj = pop.assign(y_adj=y_adj)
            ta, ca = _split(adj)
            rows.append({"population": "analysis", "metric": m, "method": "CUPED", "theta": theta, "variance_reduction": vr,
                         **st.welch(ta.y_adj.values, ca.y_adj.values, alpha)})
    ft, fc = _split(users)
    rows.append({"population": "all assigned (before SRM exclusion)", "metric": "contribution", "method": "difference in means",
                 **st.welch(ft.contribution.values, fc.contribution.values, alpha)})
    for name, (x, y) in RATIOS.items():
        mom = {v: {"mean_x": g[x].mean(), "mean_y": g[y].mean(), "var_x": g[x].var(ddof=1), "var_y": g[y].var(ddof=1),
                   "cov_xy": np.cov(g[x], g[y], ddof=1)[0, 1], "n": len(g)} for v, g in pop.groupby("variant")}
        rows.append({"population": "analysis", "metric": name, "method": "delta method (ratio)",
                     **st.ratio_diff(mom["treatment"], mom["control"], alpha)})
    results = pd.DataFrame(rows)
    _save(con, "exp_results", results)
    res = {(r.metric, r.method, r.population): r for r in results.itertuples()}
    primary = res[("contribution", "CUPED", "analysis")]

    # power: what the test could detect, raw and with CUPED
    sd = c.contribution.std(ddof=1)
    n_arm = min(len(t), len(c))
    vr = primary.variance_reduction
    power = {"n_per_arm": n_arm, "sd_contribution": sd, "control_mean": c.contribution.mean(),
             "mde_abs": st.mde(sd, n_arm, alpha, a["power"]), "mde_abs_cuped": st.mde(sd * math.sqrt(1 - vr), n_arm, alpha, a["power"]),
             "variance_reduction": vr}
    power["mde_rel"] = power["mde_abs"] / power["control_mean"]
    power["mde_rel_cuped"] = power["mde_abs_cuped"] / power["control_mean"]
    power["n_for_1pct_cuped"] = st.n_for_effect(sd * math.sqrt(1 - vr), 0.01 * power["control_mean"], alpha, a["power"])

    # novelty: effect by week since assignment and a direct test of decay (week 1 minus last week, per user)
    wk = con.execute("SELECT * FROM exp_user_week").df()
    wk = wk[wk.user_id.isin(pop.user_id)]
    nov = []
    for week, g in wk.groupby("week"):
        tw, cw = _split(g)
        for m in ["orders", "contribution"]:
            nov.append({"week": int(week), "metric": m, **st.welch(tw[m].values, cw[m].values, alpha)})
    novelty = pd.DataFrame(nov)
    _save(con, "exp_novelty", novelty)
    last = int(wk.week.max())
    piv = wk.pivot_table(index=["user_id", "variant"], columns="week", values="orders").reset_index()
    piv["decay"] = piv[1] - piv[last]
    td, cd = _split(piv)
    decay = st.welch(td.decay.values, cd.decay.values, alpha)

    # segments: CUPED within the full population, then Holm across segments per metric
    seg_rows = []
    for m in ["orders", "contribution"]:
        y_adj, _, _ = st.cuped(pop[m].values.astype(float), pop[COVARIATE[m]].values.astype(float))
        adj = pop.assign(y_adj=y_adj)
        for dim in ["platform", "zone", "tenure"]:
            for seg, g in adj.groupby(dim):
                tg, cg = _split(g)
                seg_rows.append({"metric": m, "dimension": dim, "segment": seg, **st.welch(tg.y_adj.values, cg.y_adj.values, alpha)})
    seg = pd.DataFrame(seg_rows)
    seg["p_adjusted"] = np.nan
    seg["significant_adjusted"] = False
    for m, idx in seg.groupby("metric").groups.items():
        reject, p_adj = st.holm(seg.loc[idx, "p_value"].tolist(), alpha, a["segment_correction"])
        seg.loc[idx, "p_adjusted"], seg.loc[idx, "significant_adjusted"] = p_adj, reject
    inter = []
    for m in ["orders", "contribution"]:
        for dim in ["platform", "zone", "tenure"]:
            inter.append({"metric": m, "dimension": dim, "p_value": st.interaction_test(pop, m, dim)})
    inter = pd.DataFrame(inter)
    inter["p_adjusted"], inter["significant_adjusted"] = np.nan, False
    for m, idx in inter.groupby("metric").groups.items():
        reject, p_adj = st.holm(inter.loc[idx, "p_value"].tolist(), alpha, a["segment_correction"])
        inter.loc[idx, "p_adjusted"], inter.loc[idx, "significant_adjusted"] = p_adj, reject
    _save(con, "exp_segments", seg)
    _save(con, "exp_interactions", inter)

    # bunching just above the new threshold
    thr_t, thr_c = promo_cfg["treatment_free_threshold"], promo_cfg["control_free_threshold"]
    ob = con.execute("SELECT variant, basket_value, assign_day FROM exp_orders").df()
    ob = ob[ob.assign_day.isin(pop.assign_day.unique())]
    bunch = {}
    for v, g in ob.groupby("variant"):
        bunch[v] = {"just_below": float(((g.basket_value >= thr_t - 6) & (g.basket_value < thr_t)).mean()),
                    "just_above": float(((g.basket_value >= thr_t) & (g.basket_value < thr_t + 4)).mean())}

    # decision rule on the primary metric and the margin-mix guardrail
    hm = res[("high_margin_share", "delta method (ratio)", "analysis")]
    cpo_t = res[("contribution_per_order", "delta method (ratio)", "analysis")].treatment_mean
    orders_c = res[("orders", "difference in means", "analysis")].control_mean
    breakeven = primary.control_mean / (cpo_t * orders_c) - 1
    guardrail_breached = hm.ci_high < 0
    if primary.ci_low > 0 and not guardrail_breached:
        decision = "launch"
    elif primary.ci_high < 0:
        decision = "do not launch"
    else:
        decision = "extend"
    return {
        "srm": {k: v for k, v in s.items() if k != "daily"},
        "srm_daily": s["daily"].to_dict("records"),
        "population": {"users": len(pop), "control": len(c), "treatment": len(t), "excluded_users": len(users) - len(pop)},
        "results": results.to_dict("records"), "power": power,
        "novelty": novelty.to_dict("records"), "novelty_decay_test": decay,
        "segments": seg.to_dict("records"), "interactions": inter.to_dict("records"),
        "bunching": bunch, "thresholds": {"control": thr_c, "treatment": thr_t},
        "breakeven_order_lift": breakeven, "orders_lift": res[("orders", "CUPED", "analysis")].rel_diff,
        "guardrail_high_margin_breached": bool(guardrail_breached),
        "decision": decision,
    }


def pilot(con, cfg) -> dict:
    a = cfg["analysis"]
    panel = con.execute("SELECT * FROM pilot_panel").df()
    did_rows, events, placebos = [], [], []
    for m in PILOT_METRICS:
        d = st.did(panel, m, a["alpha"])
        coefs, pre_p = st.event_study(panel, m)
        p = st.placebo(panel, m, a["placebo_offset_days"])
        slope = st.pre_trend_slope(panel, m)
        d["pre_trend_joint_p"] = pre_p
        d["pre_trend_slope_per_day"], d["pre_trend_p"] = slope["slope_per_day"], slope["p_value"]
        d["placebo_estimate"], d["placebo_p"] = p["estimate"], p["p_value"]
        did_rows.append(d)
        events.append(coefs.assign(metric=m))
    did = pd.DataFrame(did_rows)
    _save(con, "pilot_did", did)
    _save(con, "pilot_event_study", pd.concat(events, ignore_index=True))
    r = did.set_index("metric")
    cost = r.loc["cost_per_order"]
    defect_pp, sla_pp = r.loc["defect_rate"] * 100, r.loc["pct_within_sla"] * 100
    guardrails = {
        "defect_rate": {"estimate_pp": defect_pp.estimate, "ci_low_pp": defect_pp.ci_low, "ci_high_pp": defect_pp.ci_high,
                        "tolerance_pp": a["pilot_guardrail_defect_pp"],
                        "breached": bool(defect_pp.ci_low > 0 and defect_pp.estimate > a["pilot_guardrail_defect_pp"])},
        "pct_within_sla": {"estimate_pp": sla_pp.estimate, "ci_low_pp": sla_pp.ci_low, "ci_high_pp": sla_pp.ci_high,
                           "tolerance_pp": a["pilot_guardrail_sla_pp"],
                           "breached": bool(sla_pp.ci_high < 0 and sla_pp.estimate < -a["pilot_guardrail_sla_pp"])},
    }
    any_breach = any(g["breached"] for g in guardrails.values())
    cost_win = cost.ci_high < 0
    parallel_ok = bool((did.pre_trend_p > a["alpha"]).all() and (did.placebo_p > a["alpha"]).all())
    if cost_win and not any_breach and parallel_ok:
        decision = "scale"
    elif cost_win and any_breach:
        decision = "do not scale as-is: fix the guardrail and extend"
    else:
        decision = "do not scale"
    orders_per_day = panel[panel.treated].groupby("ops_date").orders.sum().mean() / panel[panel.treated].node_id.nunique()
    return {"did": did.to_dict("records"), "guardrails": guardrails, "parallel_trends_ok": parallel_ok,
            "decision": decision, "treated_nodes": int(panel[panel.treated].node_id.nunique()),
            "control_nodes": int(panel[~panel.treated].node_id.nunique()),
            "saving_per_node_day": -cost.estimate * orders_per_day,
            "extra_defects_per_node_day": defect_pp.estimate / 100 * orders_per_day,
            "orders_per_node_day": orders_per_day}


def run(con, cfg: dict) -> dict:
    findings = _clean({"promo": promo(con, cfg), "pilot": pilot(con, cfg),
                       "data_quality": con.execute("SELECT * FROM dq_report").df().to_dict("records")})
    FINDINGS.parent.mkdir(exist_ok=True)
    FINDINGS.write_text(json.dumps(findings, indent=2, sort_keys=True))
    return findings
