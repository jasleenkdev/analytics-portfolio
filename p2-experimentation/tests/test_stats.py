"""Statistical routines checked against reference implementations and simulations with known truth."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from analysis import stats as st

FINDINGS = Path(__file__).resolve().parents[1] / "outputs" / "findings.json"


def test_welch_matches_scipy():
    rng = np.random.default_rng(0)
    a, b = rng.gamma(1.2, 10, 3000), rng.gamma(1.2, 10.5, 2800)
    ours = st.welch(a, b)
    ref = stats.ttest_ind(a, b, equal_var=False)
    assert ours["p_value"] == pytest.approx(ref.pvalue, rel=1e-9)
    assert ours["diff"] == pytest.approx(a.mean() - b.mean())


def test_srm_matches_scipy_chisquare():
    assert st.srm_test(4900, 5100) == pytest.approx(stats.chisquare([4900, 5100]).pvalue)


def test_cuped_theta_is_ols_slope_and_reduces_variance():
    rng = np.random.default_rng(1)
    x = rng.gamma(1.5, 10, 5000)
    y = 0.6 * x + rng.normal(0, 5, 5000)
    y_adj, theta, vr = st.cuped(y, x)
    assert theta == pytest.approx(np.polyfit(x, y, 1)[0], rel=1e-9)
    assert vr > 0.5 and y_adj.mean() == pytest.approx(y.mean())


def test_cuped_keeps_false_positive_rate_in_aa_tests():
    rng = np.random.default_rng(2)
    hits = 0
    for _ in range(400):
        x = rng.gamma(1.5, 10, 2000)
        y = 0.5 * x + rng.gamma(1.0, 6, 2000)
        arm = rng.random(2000) < 0.5
        y_adj, _, _ = st.cuped(y, x)
        hits += st.welch(y_adj[arm], y_adj[~arm])["p_value"] < 0.05
    assert 0.02 < hits / 400 < 0.08


def test_delta_method_matches_bootstrap():
    rng = np.random.default_rng(3)
    n = 4000
    orders = rng.poisson(rng.gamma(1.3, 2, n))
    value = orders * rng.lognormal(3.4, 0.3, n)
    _, var = st.delta_ratio(value.mean(), orders.mean(), value.var(ddof=1), orders.var(ddof=1),
                            np.cov(value, orders, ddof=1)[0, 1], n)
    boot = [(lambda i: value[i].sum() / orders[i].sum())(rng.integers(0, n, n)) for _ in range(800)]
    assert np.sqrt(var) == pytest.approx(np.std(boot, ddof=1), rel=0.12)


def test_holm_adjusts_upwards():
    p = [0.001, 0.02, 0.03, 0.2]
    reject, adj = st.holm(p)
    assert (adj >= np.array(p)).all() and reject.tolist() == [True, False, False, False]


def _panel(effect: float, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    nodes, days = 20, 80
    shock = rng.normal(0, 1, days)
    rows = []
    for i in range(nodes):
        treated = i < 7
        level = rng.normal(10, 2)
        for d in range(days):
            post = d >= 40
            rows.append({"node_id": f"n{i}", "ops_date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=d),
                         "treated": treated, "post": post, "rel_day": d - 40, "rel_week": (d - 40) // 7,
                         "y": level + shock[d] + effect * (treated and post) + rng.normal(0, 0.5)})
    return pd.DataFrame(rows)


def test_did_recovers_known_effect_and_placebo_is_null():
    panel = _panel(effect=1.5)
    est = st.did(panel, "y")
    assert est["ci_low"] < 1.5 < est["ci_high"]
    assert st.placebo(panel, "y", 20)["p_value"] > 0.05
    assert st.pre_trend_slope(panel, "y")["p_value"] > 0.05
    coefs, pre_p = st.event_study(panel, "y")
    assert pre_p > 0.01
    assert coefs.loc[coefs.rel_week >= 0, "estimate"].mean() == pytest.approx(1.5, abs=0.3)


def test_pre_trend_slope_detects_diverging_groups():
    panel = _panel(effect=0.0)
    panel["y"] += np.where(panel.treated, 0.05 * panel.rel_day, 0)
    assert st.pre_trend_slope(panel, "y")["p_value"] < 0.01


def test_readout_population_passes_srm_after_exclusion():
    f = json.loads(FINDINGS.read_text())["promo"]
    if f["srm"]["detected"]:
        assert f["srm"]["after_exclusion_p"] > 0.001
        assert f["population"]["excluded_users"] > 0
    assert f["decision"] in {"launch", "do not launch", "extend"}
