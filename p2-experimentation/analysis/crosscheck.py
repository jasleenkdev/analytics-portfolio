"""Found vs planted for project 2. Runs after findings.json is frozen; the only module reading plant files."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from shared.crosscheck import load_truth, row, write

PROJECT = Path(__file__).resolve().parents[1]


def run(con, cfg: dict) -> dict:
    plants, ent, f = load_truth(PROJECT)
    p, q = f["promo"], f["pilot"]
    rows = []

    srm = plants["srm"]
    srm_date = (pd.Timestamp(cfg["sim"]["experiment_start"]) + pd.Timedelta(days=srm["day"])).date().isoformat()
    flagged = p["srm"]["flagged_dates"]
    rows.append(row(f"A1. SRM: {ent['lost_control_assignments']} control assignments lost on {srm_date}",
                    f"SRM detected (p = {p['srm']['overall_p']:.1e}); flagged day(s) {flagged}; balanced after exclusion (p = {p['srm']['after_exclusion_p']:.2f})",
                    "hit" if flagged == [srm_date] else ("partial" if srm_date in flagged else "miss")))

    pe = plants["promo_effect"]
    share_new = con.execute("SELECT avg(CAST(tenure = 'new (<90 days)' AS DOUBLE)) FROM exp_users WHERE CAST(assign_date AS VARCHAR) NOT IN (SELECT unnest(?))",
                            [flagged]).fetchone()[0]
    nov = {x["week"]: x for x in p["novelty"] if x["metric"] == "orders"}
    inside = []
    for w, lift in enumerate(pe["order_lift_by_week"], start=1):
        expected = lift + share_new * pe["new_user_extra_lift"]
        inside.append(nov[w]["rel_ci_low"] <= expected <= nov[w]["rel_ci_high"])
    est = ", ".join(f"wk{w} {nov[w]['rel_diff'] * 100:+.1f}% ({nov[w]['rel_ci_low'] * 100:+.1f} to {nov[w]['rel_ci_high'] * 100:+.1f})" for w in sorted(nov))
    exp = ", ".join(f"wk{w} {(l + share_new * pe['new_user_extra_lift']) * 100:+.1f}%" for w, l in enumerate(pe["order_lift_by_week"], start=1))
    decay_found = p["novelty_decay_test"]["p_value"] < 0.05
    rows.append(row(f"A2. novelty: order lift by week {pe['order_lift_by_week']} (+{pe['new_user_extra_lift']} for new users)",
                    f"decay test p {max(p['novelty_decay_test']['p_value'], 1e-4):.0e}{' or smaller' if p['novelty_decay_test']['p_value'] < 1e-4 else ''}; estimates {est}",
                    "hit" if decay_found and all(inside) else "partial",
                    f"expected given {share_new * 100:.0f}% new users: {exp}; {sum(inside)}/{len(inside)} weekly CIs contain the expected lift"))

    sig = sorted({x["dimension"] for x in p["interactions"] if x["significant_adjusted"]})
    rows.append(row("A3. heterogeneity: new users respond more; platform and zone do not differ",
                    f"interaction tests significant after Holm: {sig or 'none'}",
                    "hit" if sig == ["tenure"] else ("partial" if "tenure" in sig else "miss"),
                    "no false positives on platform or zone" if sig == ["tenure"] else ""))

    hm = next(x for x in p["results"] if x["metric"] == "high_margin_share" and x["population"] == "analysis")
    ratio = hm["treatment_mean"] / hm["control_mean"]
    rows.append(row(f"A4. cannibalisation: high-margin basket probability x{pe['high_margin_multiplier']}",
                    f"high-margin share {hm['control_mean'] * 100:.1f}% to {hm['treatment_mean'] * 100:.1f}% (ratio {ratio:.2f})",
                    "hit" if abs(ratio - pe["high_margin_multiplier"]) < 0.05 else "partial"))
    b = p["bunching"]
    rows.append(row(f"A5. bunching: {pe['bunching_prob'] * 100:.0f}% of baskets within {pe['bunching_window']} below the new threshold topped up",
                    f"orders just above the new threshold: {b['treatment']['just_above'] * 100:.1f}% (treatment) vs {b['control']['just_above'] * 100:.1f}% (control); "
                    f"just below: {b['treatment']['just_below'] * 100:.1f}% vs {b['control']['just_below'] * 100:.1f}%",
                    "hit" if b["treatment"]["just_above"] > b["control"]["just_above"] and b["treatment"]["just_below"] < b["control"]["just_below"] else "miss"))
    rows.append(row("A6. net truth: do not launch", f"decision: {p['decision']}", "hit" if p["decision"] == "do not launch" else "miss"))

    pl = plants["pilot_effect"]
    did = {x["metric"]: x for x in q["did"]}
    c = did["cost_per_order"]
    rows.append(row(f"B1. rider minutes per order {pl['rider_min_per_order'] * 100:+.0f}%",
                    f"cost per order {c['rel_estimate'] * 100:+.1f}% (95% CI {c['rel_ci_low'] * 100:+.1f} to {c['rel_ci_high'] * 100:+.1f})",
                    "hit" if c["rel_ci_low"] <= pl["rider_min_per_order"] <= c["rel_ci_high"] else "partial",
                    "first version divided by the pre-period level and overstated the saving (-13.0%); fixed in the cross-check to use the post-period counterfactual"))
    for metric, planted, scale, label in [("defect_rate", pl["defect_rate_pp"], 100, "defect rate pp"),
                                          ("mean_delivery_min", pl["delivery_min"], 1, "delivery minutes"),
                                          ("pct_within_sla", pl["sla_pp"], 100, "% within SLA pp")]:
        x = did[metric]
        rows.append(row(f"B2. {label} {planted:+}", f"DiD {x['estimate'] * scale:+.2f} (95% CI {x['ci_low'] * scale:+.2f} to {x['ci_high'] * scale:+.2f})",
                        "hit" if x["ci_low"] * scale <= planted <= x["ci_high"] * scale else "partial"))
    joint = [x["metric"] for x in q["did"] if x["pre_trend_joint_p"] < 0.05]
    rows.append(row("B3. parallel trends hold; placebo should be null",
                    f"linear pre-trend p >= {min(x['pre_trend_p'] for x in q['did']):.2f}; placebo p >= {min(x['placebo_p'] for x in q['did']):.2f}"
                    + (f"; joint weekly-lead test p < 0.05 for {joint}" if joint else ""),
                    "hit" if q["parallel_trends_ok"] and not joint else "partial",
                    "the joint lead test raised a false alarm with 24 clusters; the decision gate (slope and placebo) was right" if joint else ""))
    gaps = next(x for x in f["data_quality"] if x["check_name"].startswith("pilot node-days missing"))
    planted_gap = len(plants["pilot_data_quality"]["missing_days"]) * plants["pilot_data_quality"]["control_nodes_with_gaps"]
    rows.append(row(f"B4. {planted_gap} missing node-days at {ent['pilot_nodes_with_gaps']}",
                    f"{gaps['failing_rows']} missing node-days found; panel kept unbalanced",
                    "hit" if gaps["failing_rows"] == planted_gap else "partial", "count found; the node is not named in the report"))
    rows.append(row("B5. net truth: do not scale as-is", f"decision: {q['decision']}", "hit" if q["decision"].startswith("do not scale as-is") else "miss"))
    return write(PROJECT, rows)
