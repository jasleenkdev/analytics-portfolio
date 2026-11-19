"""Retention-driver model, funnel drop-off detection and the findings file for project 3."""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import proportions_ztest

PROJECT = Path(__file__).resolve().parents[1]
FINDINGS = PROJECT / "outputs" / "findings.json"
TRANSITIONS = [("sessions", "add_to_cart", "session_to_cart"), ("add_to_cart", "checkout", "cart_to_checkout"),
               ("checkout", "payment_attempt", "checkout_to_payment"), ("payment_attempt", "order_placed", "payment_success")]


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
    if isinstance(v, (list, tuple, np.ndarray)):
        return [_clean(x) for x in v]
    return v


def _save(con, name: str, df: pd.DataFrame) -> None:
    con.register("tmp_df", df)
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp_df")
    con.unregister("tmp_df")


def funnel_dropoffs(con, cfg) -> pd.DataFrame:
    """Each platform x version x step conversion against all other segments pooled (two-proportion z, Holm)."""
    seg = con.execute("""SELECT platform, app_version, sum(sessions) AS sessions, sum(add_to_cart) AS add_to_cart,
                         sum(checkout) AS checkout, sum(payment_attempt) AS payment_attempt, sum(order_placed) AS order_placed
                         FROM funnel_segment_month GROUP BY ALL""").df()
    rows = []
    for (frm, to, name) in TRANSITIONS:
        tot_n, tot_k = seg[frm].sum(), seg[to].sum()
        for r in seg.itertuples():
            n, k = getattr(r, frm), getattr(r, to)
            on, ok = tot_n - n, tot_k - k
            _, p = proportions_ztest([k, ok], [n, on])
            rows.append({"platform": r.platform, "app_version": r.app_version, "step": name, "entering": int(n),
                         "rate": k / n, "others_rate": ok / on, "gap_pp": (k / n - ok / on) * 100, "p_value": p})
    df = pd.DataFrame(rows)
    df["p_adjusted"] = multipletests(df.p_value, method="holm")[1]
    df["flagged"] = (df.p_adjusted < cfg["analysis"]["alpha"]) & (df.gap_pp <= -cfg["assortment"]["funnel_min_gap_pp"])
    return df.sort_values("gap_pp", ignore_index=True)


def onset(con, platform: str, version: str) -> dict:
    """First day the flagged version took payments, and the platform's daily success before and after."""
    d = con.execute("""SELECT session_date, app_version, sum(payment_attempts) AS att, sum(orders) AS ok
                       FROM funnel_daily_payment WHERE platform = ? GROUP BY ALL ORDER BY session_date""", [platform]).df()
    first_day = d.loc[d.app_version == version, "session_date"].min()
    plat = d.groupby("session_date")[["att", "ok"]].sum()
    before = plat[plat.index < first_day]
    after = plat[plat.index >= first_day + pd.Timedelta(days=28)]
    return {"first_day": first_day, "platform_success_before": before.ok.sum() / before.att.sum(),
            "platform_success_after_full_adoption": after.ok.sum() / after.att.sum()}


def retention_model(con, cfg) -> pd.DataFrame:
    """Logistic regression of 90-day repeat on acquisition channel, first-order experience, platform and first basket."""
    df = con.execute("""
        SELECT c.acquisition_channel, c.platform, CAST(c.first_order_issue AS INTEGER) AS first_order_issue,
               ln(f.revenue) AS log_first_basket,
               CAST(coalesce(date_diff('day', c.first_order_ts, c.second_order_ts) <= 90, false) AS INTEGER) AS repeat_90d
        FROM customer_facts c JOIN order_facts f ON f.customer_id = c.customer_id AND f.order_seq = 1
        WHERE date_diff('day', c.first_order_ts, CAST(? AS TIMESTAMP)) >= 90""", [cfg["analysis"]["as_of_date"]]).df()
    model = smf.logit("repeat_90d ~ C(acquisition_channel, Treatment('organic')) + first_order_issue"
                      " + C(platform, Treatment('ios')) + log_first_basket", data=df).fit(disp=False)
    me = model.get_margeff(at="overall").summary_frame()
    out = pd.DataFrame({
        "term": me.index, "marginal_effect_pp": me["dy/dx"].values * 100,
        "ci_low_pp": me["Conf. Int. Low"].values * 100, "ci_high_pp": me["Cont. Int. Hi."].values * 100,
        "p_value": me["Pr(>|z|)"].values,
        "odds_ratio": np.exp(model.params.reindex(me.index).values),
    })
    out["term"] = (out.term.str.replace(r"C\(acquisition_channel, Treatment\('organic'\)\)\[T\.(.*)\]", r"channel: \1 (vs organic)", regex=True)
                   .str.replace(r"C\(platform, Treatment\('ios'\)\)\[T\.(.*)\]", r"platform: \1 (vs ios)", regex=True))
    out.attrs["n"], out.attrs["base_rate"] = len(df), df.repeat_90d.mean()
    return out


def collect(con, cfg) -> dict:
    q = lambda sql, p=None: con.execute(sql, p or []).df()  # noqa: E731
    drops = funnel_dropoffs(con, cfg)
    _save(con, "funnel_dropoffs", drops)
    flagged = drops[drops.flagged]
    dropoff = None
    if len(flagged):
        top = flagged.iloc[0]
        on = onset(con, top.platform, top.app_version)
        aov = q("""SELECT avg(o.order_value) AS aov FROM orders o JOIN sessions s USING (session_id)
                   WHERE s.platform = ?""", [top.platform]).aov.iloc[0]
        lost = top.entering * (top.others_rate - top.rate)
        dropoff = {**top.to_dict(), **on, "lost_orders": lost, "lost_revenue": lost * aov, "aov": aov}

    model = retention_model(con, cfg)
    _save(con, "retention_model", model)
    rc = q("SELECT * FROM repeat_curve").set_index("days").repeat_rate
    cohort = q("""SELECT months_since_first, sum(active_customers) / sum(cohort_size) AS retention
                  FROM cohort_retention WHERE cohort_month <= (SELECT max(cohort_month) - INTERVAL 6 MONTH FROM cohort_retention)
                  GROUP BY 1 ORDER BY 1""").set_index("months_since_first").retention
    drivers = q("SELECT * FROM retention_drivers")
    rfm = q("SELECT * FROM rfm_segments")
    abc = q("SELECT * FROM abc_xyz_matrix")
    aff = q("""SELECT * FROM basket_affinity WHERE lift >= ? ORDER BY lift DESC""", [cfg["analysis"]["affinity_min_lift"]])
    waste = q("SELECT sum(waste_cost) AS cost, sum(units_wasted) / sum(units_received) AS rate FROM wastage_node_sku").iloc[0]
    reduce_ = q("SELECT * FROM assortment_reduce ORDER BY waste_cost DESC, node_id, sku_id")
    adds = q("""SELECT a.*, x.abc, x.units AS network_units FROM assortment_add a JOIN abc_xyz x USING (sku_id)
                ORDER BY impact_high DESC""")
    add_skus = adds.groupby(["sku_id", "category"]).agg(nodes=("node_id", "count"), impact_low=("impact_low", "sum"),
                                                         impact_high=("impact_high", "sum"), margin_rate=("margin_rate", "first"),
                                                         abc=("abc", "first"), ranged_nodes=("ranged_nodes", "first")).reset_index() \
        .sort_values("impact_high", ascending=False)
    summary = q("SELECT action, count(*) AS recs, sum(impact_low) AS impact_low, sum(impact_high) AS impact_high FROM assortment_recommendations GROUP BY 1")
    per_node = q("SELECT * FROM assortment_node_summary")
    median_velocity = q("SELECT median(units_per_ranged_node_week) AS v FROM abc_xyz").v.iloc[0]
    return _clean({
        "funnel": {"overall": q("SELECT * FROM funnel_overall").to_dict("records"), "dropoff": dropoff,
                   "flagged": flagged.to_dict("records"), "tests": int(len(drops))},
        "retention": {"repeat_curve": rc.to_dict(), "cohort_curve": cohort.to_dict(), "drivers": drivers.to_dict("records"),
                      "model": model.to_dict("records"), "model_n": model.attrs["n"], "model_base_rate": model.attrs["base_rate"],
                      "customers": int(q("SELECT count(*) AS n FROM customer_facts").n.iloc[0])},
        "rfm": rfm.to_dict("records"),
        "abc_xyz": abc.to_dict("records"),
        "affinity": aff.head(15).to_dict("records"), "affinity_pairs_strong": int(len(aff)),
        "wastage": {"total_cost": waste.cost, "waste_rate": waste.rate, "reduce": reduce_.head(20).to_dict("records"),
                    "reduce_count": int(len(reduce_)), "reduce_cost": reduce_.waste_cost.sum(),
                    "top_node_category": q("SELECT * FROM wastage_node_category LIMIT 6").to_dict("records")},
        "assortment": {"summary": summary.to_dict("records"), "per_node": per_node.to_dict("records"),
                       "add_skus": add_skus.head(12).to_dict("records"), "median_velocity": median_velocity},
        "data_quality": q("SELECT * FROM dq_report").to_dict("records"),
    })


def run(con, cfg: dict) -> dict:
    f = collect(con, cfg)
    FINDINGS.parent.mkdir(exist_ok=True)
    FINDINGS.write_text(json.dumps(f, indent=2, sort_keys=True))
    return f
