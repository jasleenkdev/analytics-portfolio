"""Assortment rules, funnel drop-off detection and the retention model checked against their definitions."""
import json
from pathlib import Path

import numpy as np
import pytest

from conftest import scalar

FINDINGS = Path(__file__).resolve().parents[1] / "outputs" / "findings.json"


def test_add_recommendations_respect_rules(con):
    assert scalar(con, """SELECT count(*) FROM assortment_add a JOIN node_range r USING (node_id, sku_id)""") == 0
    bad = scalar(con, """SELECT count(*) FROM assortment_add WHERE expected_margin_week < cat_median_margin_week
                         OR impact_low > impact_high OR ranged_nodes < 1""")
    assert bad == 0


def test_add_impact_formula(con, cfg):
    row = con.execute("SELECT * FROM assortment_add ORDER BY impact_high DESC LIMIT 1").df().iloc[0]
    perf = con.execute("SELECT p.node_id, p.margin_per_week, s.scale FROM node_sku_perf p JOIN node_scale s USING (node_id) WHERE sku_id = ?",
                       [row.sku_id]).df()
    scale = scalar(con, "SELECT scale FROM node_scale WHERE node_id = ?", [row.node_id])
    norm = perf.margin_per_week / perf.scale
    assert row.impact_high == pytest.approx(52 * norm.max() * scale, rel=1e-9)
    assert row.impact_low == pytest.approx(52 * norm.min() * scale * (1 - cfg["assortment"]["cannibalisation_low"]), rel=1e-9)


def test_drop_recommendations_respect_rules(con, cfg):
    assert scalar(con, "SELECT count(*) FROM assortment_drop d WHERE NOT EXISTS (SELECT 1 FROM node_range r WHERE r.node_id = d.node_id AND r.sku_id = d.sku_id)") == 0
    assert scalar(con, "SELECT count(*) FROM assortment_drop WHERE abc <> 'C'") == 0
    strong = scalar(con, """SELECT count(*) FROM assortment_drop d JOIN basket_affinity b
                            ON (d.sku_id = b.sku_a OR d.sku_id = b.sku_b) AND b.lift >= ?""", [cfg["analysis"]["affinity_min_lift"]])
    assert strong == 0


def test_reduce_recommendations_respect_rules(con, cfg):
    bad = scalar(con, "SELECT count(*) FROM assortment_reduce WHERE risk_score < ? OR avg_daily_sold < ? OR impact_low > impact_high",
                 [cfg["analysis"]["wastage_risk_threshold"], cfg["assortment"]["reduce_min_daily_units"]])
    assert bad == 0


def test_funnel_dropoff_test_statistics(con, cfg):
    d = con.execute("SELECT * FROM funnel_dropoffs").df()
    assert (d.p_adjusted >= d.p_value - 1e-15).all()
    flagged = d[d.flagged]
    assert (flagged.gap_pp <= -cfg["assortment"]["funnel_min_gap_pp"]).all() and (flagged.p_adjusted < cfg["analysis"]["alpha"]).all()
    pay = d[d.step == "payment_success"]
    totals = con.execute("SELECT platform, app_version, sum(payment_attempt) a, sum(order_placed) o FROM funnel_segment_month GROUP BY ALL").df()
    for r in pay.itertuples():
        t = totals[(totals.platform == r.platform) & (totals.app_version == r.app_version)].iloc[0]
        rest = totals.drop(t.name)
        assert r.rate == pytest.approx(t.o / t.a) and r.others_rate == pytest.approx(rest.o.sum() / rest.a.sum())


def test_retention_model_agrees_with_raw_rates(con):
    f = json.loads(FINDINGS.read_text())["retention"]
    raw = {d["level"]: d["repeat_rate_90d"] for d in f["drivers"] if d["driver"] == "first_order_experience"}
    gap_pp = (raw["problem on first order"] - raw["clean first order"]) * 100
    model = {m["term"]: m for m in f["model"]}["first_order_issue"]
    assert np.sign(model["marginal_effect_pp"]) == np.sign(gap_pp)
    assert abs(model["marginal_effect_pp"] - gap_pp) < 3
